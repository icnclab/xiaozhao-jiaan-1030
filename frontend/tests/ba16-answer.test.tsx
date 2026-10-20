import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnswerCard } from '../src/liff/components';
import type { Answer } from '../src/api';

afterEach(cleanup);
it('shows the cited medication fact and a separate policy notice on the actual answer card', () => {
  const answer: Answer = {id:'qa',created_at:'',outcome:'answered',label:'AI 初步參考',
    question_masked:'可以幫忙買藥嗎？',answer_text:'unused assembled text',
    claims:[{text:'BA16 代購項目的目的物品包括藥品。',citations:['c1','c2']}],citations:[],
    safety_notice:'用藥界線（系統安全提醒）：不可自行決定用量，請由醫療專業人員確認。',
    escalation_reason:null,escalation_reason_text:null,case:null,manual_case:null,case_error:null,
    feedback_wrong:false,tts:null,modes:{llm:'ollama'},qa_policy_version:'test',wake_word:false};
  render(<MemoryRouter><AnswerCard answer={answer} onChange={() => {}} /></MemoryRouter>);
  expect(screen.getByText('BA16 代購項目的目的物品包括藥品。')).toBeTruthy();
  expect(screen.getByText('（出處 1、2）')).toBeTruthy();
  expect(screen.getByText(/用藥界線（系統安全提醒）/)).toBeTruthy();
});

it.each(['可以幫忙買藥嗎？', '可以代領藥嗎？', '照服員可以幫忙買藥嗎？'])
('keeps every source card and one safety notice with concise claims: %s', (question) => {
  const answer: Answer = {id:'qa',created_at:'',outcome:'answered',label:'AI 初步參考',
    question_masked:question,answer_text:'assembled',
    claims:[{text:'依 BA16 服務範圍，可以協助代購／代領／代送藥品。',citations:['c1','c2']},
      {text:'上述目的物品或事項應為長照給付對象本身所需。',citations:['c2']},
      {text:'距離自案家出門起算五公里內適用本組合，超出範圍的所需費用由長照給付對象自行負擔。',citations:['c2']}],
    citations:[1,2,3].map(i => ({id:`cite${i}`,chunk_id:`chunk${i}`,version_id:'version',
      document_title:'附表四 照顧組合表',doc_type:'official',locator:`第 ${i} 頁`,version_label:'v1',
      effective_from:null,effective_to:null,version_status:'published',source:null,source_url:'/source',
      external_url:null,excerpt:`完整原始引用 ${i}`})),
    safety_notice:'用藥界線（系統安全提醒）：不得自行決定藥品、用量、服法或給藥；請由督導與醫療專業人員確認。',
    escalation_reason:null,escalation_reason_text:null,case:null,manual_case:null,case_error:null,
    feedback_wrong:false,tts:null,modes:{llm:'ollama'},qa_policy_version:'test',wake_word:false};
  const {container} = render(<MemoryRouter><AnswerCard answer={answer} onChange={() => {}} /></MemoryRouter>);
  const body = Array.from(container.querySelectorAll('.claim')).map(e => e.textContent).join('');
  expect(body.match(/五公里/g)).toHaveLength(1);
  expect(body.match(/本身所需/g)).toHaveLength(1);
  expect(body.match(/藥品/g)).toHaveLength(1);
  expect(container.querySelectorAll('.cite')).toHaveLength(3);
  expect(screen.getAllByText(/用藥界線（系統安全提醒）/)).toHaveLength(1);
  expect(screen.getByText('完整原始引用 3')).toBeTruthy();
});

it('keeps the emergency escalation notice on risk answers', () => {
  const answer: Answer = {id:'qa',created_at:'',outcome:'escalated',label:'轉人工',
    question_masked:'胸痛又喘',answer_text:'請立即依機構緊急應變程序處理，並通知在場護理人員。系統無法直接回答。',
    claims:[],citations:[],escalation_reason:'risk_emergency',escalation_reason_text:'安全風險',
    case:null,manual_case:null,case_error:null,feedback_wrong:false,tts:null,modes:{llm:'ollama'},
    qa_policy_version:'test',wake_word:false};
  render(<MemoryRouter><AnswerCard answer={answer} onChange={() => {}} /></MemoryRouter>);
  expect(screen.getByText(/立即依機構緊急應變程序處理/)).toBeTruthy();
});
