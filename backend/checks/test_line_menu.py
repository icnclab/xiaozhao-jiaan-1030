"""Isolated unittest: execute actual function bodies without importing app/DB.

Run directly with python -B; never loads backend/tests/conftest.py or .env.
"""
import ast
import copy
import ipaddress
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace, constants=()):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    nodes = [n for n in tree.body if
             isinstance(n, ast.FunctionDef) and n.name in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    # Postpone annotations: no application imports, engine creation or settings reads.
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future] + nodes, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


class LineMenuTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(public_base_url="https://care.example.org")
        self.client = Mock()
        self.ai = SimpleNamespace(ask=Mock(side_effect=AssertionError("AI must not run")))
        self.ns = {
            "urlsplit": urlsplit, "ipaddress": ipaddress,
            "get_settings": lambda: self.settings,
            "get_line_client": lambda session: self.client,
            "qa_service": self.ai,
            "strip_wake_word": Mock(return_value=SimpleNamespace(greeting_only=False)),
            "greeting_reply": lambda: "原本招呼",
        }
        load_functions(ROOT / "app/services/notifications.py", {"liff_url"}, self.ns)
        load_functions(ROOT / "app/line/service.py",
                       {"_function_menu", "_on_text", "_text", "process_event"}, self.ns,
                       {"MENU_KEYWORDS"})
        self.event = SimpleNamespace(reply_token="fake-reply", webhook_event_id="fake-event")

    def send(self, text):
        return self.ns["_on_text"](Mock(), self.event, object(), text)

    def reply_text(self):
        messages = self.client.reply.call_args.args[1]
        self.assertEqual(len(messages), 1)
        self.assertEqual(set(messages[0]), {"type", "text"})
        self.assertEqual(messages[0]["type"], "text")
        return messages[0]["text"]

    def menu_message(self):
        messages = self.client.reply.call_args.args[1]
        self.assertEqual(len(messages), 1)
        return messages[0]

    def validate_menu_contract(self, message):
        # Offline contract for the official fields we use, not a server validation.
        # https://developers.line.biz/en/reference/messaging-api/
        self.assertEqual(set(message), {"type", "altText", "contents", "quickReply"})
        self.assertEqual(message["type"], "flex")
        self.assertTrue(0 < len(message["altText"]) <= 400)
        bubble = message["contents"]
        self.assertEqual(set(bubble), {"type", "body", "footer"})
        self.assertEqual(bubble["type"], "bubble")
        for block in (bubble["body"], bubble["footer"]):
            self.assertEqual(set(block), {"type", "layout", "spacing", "contents"})
            self.assertEqual(block["type"], "box")
            self.assertEqual(block["layout"], "vertical")
            self.assertEqual(block["spacing"], "sm")
        items = message["quickReply"]["items"]
        self.assertEqual(set(message["quickReply"]), {"items"})
        self.assertEqual(len(items), 5)
        self.assertLessEqual(len(items), 13)
        buttons = bubble["footer"]["contents"]
        self.assertEqual(len(buttons), 5)
        for item, button in zip(items, buttons):
            self.assertEqual(set(item), {"type", "action"})
            self.assertEqual(item["type"], "action")
            self.assertEqual(set(button), {"type", "style", "color", "height", "action"})
            self.assertEqual(button["type"], "button")
            self.assertEqual(button["style"], "primary")
            self.assertEqual(button["color"], "#263238")
            self.assertEqual(button["height"], "sm")
            self.assertEqual(button["action"], item["action"])
            action = item["action"]
            self.assertEqual(set(action), {"type", "label", "uri"})
            self.assertEqual(action["type"], "uri")
            self.assertTrue(0 < len(action["label"]) <= 20)
            self.assertTrue(action["uri"].startswith("https://"))
            self.assertLessEqual(len(action["uri"]), 1000)
        # Ensure transport payload can be encoded as JSON.
        self.assertEqual(json.loads(json.dumps(message)), message)

    def test_three_commands(self):
        for text in ("選單", "功能", "幫助"):
            with self.subTest(text=text):
                self.assertEqual(self.send(text), "menu")
                self.validate_menu_contract(self.menu_message())
                self.assertTrue(self.menu_message()["altText"].startswith("小照｜功能選單"))
        self.ai.ask.assert_not_called()

    def test_surrounding_whitespace(self):
        for text in (" 選單 ", "\t功能\n", "　幫助　"):
            self.assertEqual(self.send(text), "menu")
        self.ai.ask.assert_not_called()

    def test_five_real_routes_and_labels(self):
        self.send("選單")
        message = self.menu_message()
        self.validate_menu_contract(message)
        actions = [item["action"] for item in message["quickReply"]["items"]]
        urls = [action["uri"] for action in actions]
        self.assertEqual(urls, [f"https://care.example.org/liff/{p}"
                                for p in ("ask", "record", "report", "cases", "help")])
        self.assertEqual([a["label"] for a in actions], ["問 AI", "錄音／談話", "問題分類", "我的案件", "使用說明"])
        visible = "\n".join(t["text"] for t in message["contents"]["body"]["contents"])
        self.assertEqual(visible, "小照｜功能選單\n請點選下方按鈕使用功能。")
        self.assertNotIn("http", visible + message["altText"])
        routes = (ROOT.parent / "frontend/src/main.tsx").read_text(encoding="utf-8")
        for page in ("ask", "report", "cases", "help", "record"):
            self.assertIn(f'path: "{page}"', routes)

    def test_normal_questions_keep_original_flow(self):
        error = type("FakeQaError", (Exception,), {})
        self.ai.QaError = error
        self.ai.ask.side_effect = error("原流程回覆")
        for text in ("這個功能怎麼使用？", "選單在哪裡", "幫助我", "功能。"):
            with self.subTest(text=text):
                self.assertEqual(self.send(text), "invalid")
                self.assertEqual(self.ai.ask.call_args.kwargs["question"], text)
                self.assertEqual(self.reply_text(), "原流程回覆")

    def test_unbound_commands_keep_binding_gate(self):
        for command in ("選單", "功能", "幫助"):
            event = SimpleNamespace(status="received", payload_encrypted="fake",
                                    line_user_id="fake-user", event_type="message", message_type="text",
                                    reply_token="fake-reply")
            self.ns.update(decrypt_json=lambda _: {"text": command},
                           _user_for=lambda *_: None, LineEvent=object,
                           jobs=SimpleNamespace(utcnow=lambda: "fake-time"))
            self.ns["process_event"](Mock(get=Mock(return_value=event)), "fake-id")
            self.assertEqual(event.error, "unbound")
            self.assertIn("尚未綁定", self.reply_text())
            self.assertIn("https://care.example.org/liff/bind", self.reply_text())
            self.assertNotIn("小照｜功能選單", self.reply_text())
        self.ai.ask.assert_not_called()

    def test_existing_commands(self):
        for command, (page, label) in self.ns["MENU_KEYWORDS"].items():
            self.assertEqual(self.send(command), "menu")
            self.assertEqual(self.reply_text(), f"{label}：https://care.example.org/liff/{page}")
        self.ai.ask.assert_not_called()

    def test_greeting_unchanged(self):
        self.ns["strip_wake_word"].return_value.greeting_only = True
        self.assertEqual(self.send("小照你好"), "greeting")
        message = self.client.reply.call_args.args[1][0]
        self.assertEqual(message["text"], "原本招呼")
        self.assertEqual(len(message["quickReply"]["items"]), 3)
        self.ai.ask.assert_not_called()

    def test_invalid_base_never_emits_links(self):
        for base in ("", None, "http://care.example.org", "javascript:alert(1)",
                     "https://", "https://localhost", "https://127.0.0.1",
                     "https://care.local", "https://user:pass@care.example.org",
                     "https://care.example.org?x=1", "https://care.example.org/#x",
                     "https://care.example.org/wrong", "https://care.example.org:bad",
                     "https://bad_host.example.org", "https://bad..example.org",
                     "https://care.example.org\n", "https://care.example.org\\evil",
                     "https://care.example.org%0a.evil"):
            with self.subTest(base=base):
                self.settings.public_base_url = base
                self.send("選單")
                self.assertEqual(self.reply_text(), "小照｜功能選單\n功能連結暫時無法使用，請聯絡督導協助。")
        self.ai.ask.assert_not_called()

    def test_trailing_slash(self):
        self.settings.public_base_url += "/"
        self.send("功能")
        action = self.menu_message()["quickReply"]["items"][0]["action"]
        self.assertEqual(action["uri"], "https://care.example.org/liff/ask")

    def test_malformed_generated_link(self):
        self.ns["liff_url"] = lambda _: "http://wrong.example.org"
        self.send("選單")
        self.assertNotIn("http", self.reply_text())
        self.assertIn("請聯絡督導", self.reply_text())

    def test_exactly_one_reply_and_no_queries(self):
        session = Mock()
        self.ns["_on_text"](session, self.event, object(), "選單")
        self.client.reply.assert_called_once()
        session.assert_not_called()
        self.assertEqual(session.mock_calls, [])
        self.ai.ask.assert_not_called()
        self.ns["strip_wake_word"].assert_not_called()

    def test_invalid_message_fields_detected(self):
        self.send("選單")
        original = self.menu_message()
        def missing_alt(m): del m["altText"]
        def wrong_type(m): m["type"] = "text"
        def misspelled_quick(m): m["quick_reply"] = m.pop("quickReply")
        def bad_action(m): m["quickReply"]["items"][0]["action"]["type"] = "message"
        def missing_uri(m): del m["quickReply"]["items"][0]["action"]["uri"]
        def long_label(m): m["quickReply"]["items"][0]["action"]["label"] = "字" * 21
        def too_many(m): m["quickReply"]["items"] *= 3
        def bad_button(m): m["contents"]["footer"]["contents"][0]["type"] = "bad"
        for mutate in (missing_alt, wrong_type, misspelled_quick, bad_action, missing_uri, long_label, too_many, bad_button):
            with self.subTest(mutation=mutate.__name__):
                message = copy.deepcopy(original)
                mutate(message)
                with self.assertRaises((AssertionError, KeyError)):
                    self.validate_menu_contract(message)

    def test_without_reply_token_sends_nothing(self):
        self.event.reply_token = None
        self.assertEqual(self.send("選單"), "menu")
        self.client.reply.assert_not_called()
        self.ai.ask.assert_not_called()

    def test_real_client_preserves_payload_without_network(self):
        # Execute the real HTTP adapter with a fake transport; never import app or read .env.
        path = ROOT / "app/line/client.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RealLineClient")
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        fake_http = SimpleNamespace(post=Mock(return_value=SimpleNamespace(status_code=200)), HTTPError=RuntimeError)
        ns = {"httpx": fake_http, "API_BASE": "https://api.line.me", "_classify": lambda code: code}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[future, cls], type_ignores=[])), str(path), "exec"), ns)
        self.send("選單")
        message = self.menu_message()
        client = ns["RealLineClient"]("synthetic-token")
        self.assertEqual(client.reply("synthetic-reply", [message]), 200)
        fake_http.post.assert_called_once()
        call = fake_http.post.call_args
        self.assertEqual(call.args[0], "https://api.line.me/v2/bot/message/reply")
        self.assertEqual(call.kwargs["json"], {"replyToken": "synthetic-reply", "messages": [message]})
        self.validate_menu_contract(call.kwargs["json"]["messages"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
