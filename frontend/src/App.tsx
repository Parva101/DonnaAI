import { Routes, Route, Navigate } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { OAuthCallbackPage } from "@/pages/OAuthCallbackPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { InboxPage } from "@/pages/InboxPage";
import { EmailPage } from "@/pages/EmailPage";
import { VoicePage } from "@/pages/VoicePage";
import { CalendarPage } from "@/pages/CalendarPage";
import { NewsPage } from "@/pages/NewsPage";
import { SettingsPage } from "@/pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="oauth/callback" element={<OAuthCallbackPage />} />
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="email" element={<EmailPage />} />
        <Route path="voice" element={<VoicePage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="news" element={<NewsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
