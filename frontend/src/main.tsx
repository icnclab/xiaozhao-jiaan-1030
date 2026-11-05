import React from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import "./styles.css";
import { LiffApp } from "./liff/LiffApp";
import { AdminApp } from "./admin/AdminApp";
import { HomePage } from "./liff/pages/HomePage";
import { AskPage } from "./liff/pages/AskPage";
import { AnswerPage } from "./liff/pages/AnswerPage";
import { RecordPage } from "./liff/pages/RecordPage";
import { TranscriptPage } from "./liff/pages/TranscriptPage";
import { ReportPage } from "./liff/pages/ReportPage";
import { ReportEntryPage } from "./liff/pages/ReportEntryPage";
import { ReportPreviewPage } from "./liff/pages/ReportPreviewPage";
import { CasesPage } from "./liff/pages/CasesPage";
import { CaseDetailPage } from "./liff/pages/CaseDetailPage";
import { HelpPage } from "./liff/pages/HelpPage";
import { BindPage } from "./liff/pages/BindPage";
import { MpcReviewPage } from "./liff/pages/MpcReviewPage";
import { AdminLoginPage } from "./admin/pages/AdminLoginPage";
import { AdminCasesPage } from "./admin/pages/AdminCasesPage";
import { AdminCaseDetailPage } from "./admin/pages/AdminCaseDetailPage";
import { AdminDocumentsPage } from "./admin/pages/AdminDocumentsPage";
import { AdminCategoriesPage } from "./admin/pages/AdminCategoriesPage";
import { AdminMetricsPage } from "./admin/pages/AdminMetricsPage";
import { AdminFeedbackPage } from "./admin/pages/AdminFeedbackPage";
import { AdminUsersPage } from "./admin/pages/AdminUsersPage";
import { AdminAuditPage } from "./admin/pages/AdminAuditPage";
import { AdminCatalogPage } from "./admin/pages/AdminCatalogPage";
import { AdminFormPreviewPage } from "./admin/pages/AdminFormPreviewPage";
import { AdminSimulatorPage } from "./admin/pages/AdminSimulatorPage";

const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/liff" replace /> },
  {
    path: "/liff",
    element: <LiffApp />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "ask", element: <AskPage /> },
      { path: "answers/:id", element: <AnswerPage /> },
      { path: "record", element: <RecordPage /> },
      { path: "record/:id", element: <TranscriptPage /> },
      { path: "report", element: <ReportPage /> },
      { path: "report/entry", element: <ReportEntryPage /> },
      { path: "report/preview", element: <ReportPreviewPage /> },
      { path: "cases", element: <CasesPage /> },
      { path: "cases/:id", element: <CaseDetailPage /> },
      { path: "help", element: <HelpPage /> },
      { path: "bind", element: <BindPage /> },
      { path: "mpc-review", element: <MpcReviewPage /> },
    ],
  },
  {
    path: "/admin",
    element: <AdminApp />,
    children: [
      { index: true, element: <Navigate to="/admin/cases" replace /> },
      { path: "login", element: <AdminLoginPage /> },
      { path: "cases", element: <AdminCasesPage /> },
      { path: "cases/:id", element: <AdminCaseDetailPage /> },
      { path: "documents", element: <AdminDocumentsPage /> },
      { path: "categories", element: <AdminCategoriesPage /> },
      { path: "metrics", element: <AdminMetricsPage /> },
      { path: "feedback", element: <AdminFeedbackPage /> },
      { path: "users", element: <AdminUsersPage /> },
      { path: "audit", element: <AdminAuditPage /> },
      { path: "catalog", element: <AdminCatalogPage /> },
      { path: "catalog/preview/:code", element: <AdminFormPreviewPage /> },
      { path: "simulator", element: <AdminSimulatorPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
