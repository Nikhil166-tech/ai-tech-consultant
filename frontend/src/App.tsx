import React, { useState, useEffect } from "react";
import { Navbar } from "./components/Navbar";
import { Sidebar, ViewType } from "./components/Sidebar";
import { DashboardView } from "./components/DashboardView";
import { GmailInboxView } from "./components/GmailInboxView";
import { KnowledgeChatView } from "./components/KnowledgeChatView";
import { KnowledgeBrainView } from "./components/KnowledgeBrainView";
import { SitemapManagementView } from "./components/SitemapManagementView";
import { RefreshRunsView } from "./components/RefreshRunsView";
import { QuarantineView } from "./components/QuarantineView";
import { AnalyticsView } from "./components/AnalyticsView";
import { AIIntelligenceView } from "./components/AIIntelligenceView";
import { MeetingToSOWView } from "./components/MeetingToSOWView";
import { SettingsView } from "./components/SettingsView";
import { AuthModal } from "./components/AuthModal";
import { ComposeModal } from "./components/ComposeModal";
import { api } from "./api";
import {
  User,
  SitemapItem,
  IndexingEstimate,
  RefreshRunSummary,
  QuarantineRecord,
  InteractionRecord,
  LabelAutonomyState,
  TaxonomyItem,
  GmailAccountStatus,
  CustomerEmail
} from "./types";

export function App() {
  const [currentView, setCurrentView] = useState<ViewType>("dashboard");
  const [user, setUser] = useState<User | null>(null);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [isSyncingGmail, setIsSyncingGmail] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");

  // Data states
  const [sitemaps, setSitemaps] = useState<SitemapItem[]>([]);
  const [articles, setArticles] = useState<any[]>([]);
  const [refreshRuns, setRefreshRuns] = useState<RefreshRunSummary[]>([]);
  const [quarantined, setQuarantined] = useState<QuarantineRecord[]>([]);
  const [interactions, setInteractions] = useState<InteractionRecord[]>([]);
  const [labelStates, setLabelStates] = useState<LabelAutonomyState[]>([]);
  const [autonomySettings, setAutonomySettings] = useState<any>({ defaultThreshold: 3, emergencyStop: false });
  const [userSettings, setUserSettings] = useState<any>({
    url_verification_threshold: 3,
    sitemap_refresh_frequency: "daily",
    quarantine_action_rule: "QUARANTINE_ON_CONSECUTIVE_FAILURES"
  });
  const [taxonomy, setTaxonomy] = useState<TaxonomyItem[]>([]);
  const [gmailStatus, setGmailStatus] = useState<GmailAccountStatus>({ isConnected: false });
  const [feedbackMetrics, setFeedbackMetrics] = useState<any>({
    totalReviews: 0,
    unchangedCount: 0,
    editCount: 0,
    rejectCount: 0,
    unchangedRate: 0,
    editRate: 0,
    rejectRate: 0
  });
  const [feedbackHistory, setFeedbackHistory] = useState<any[]>([]);
  const [indexingEstimate, setIndexingEstimate] = useState<IndexingEstimate | null>(null);

  // Load all initial data from both backend services
  const loadData = async () => {
    try {
      // 1. Auth status
      try {
        const uRes = await api.getCurrentUser();
        if (uRes?.user) setUser(uRes.user);
      } catch {
        // Unauthenticated is allowed
      }

      // 2. Task 1 Knowledge Brain data
      try {
        const [smRes, artRes, qRes, runsRes, estRes, uSetRes] = await Promise.allSettled([
          api.listSitemaps(),
          api.listArticles(),
          api.listQuarantinedArticles(),
          api.listRefreshRuns(),
          api.getIndexingEstimate(),
          api.getUserSettings()
        ]);
        if (smRes.status === "fulfilled" && Array.isArray(smRes.value)) setSitemaps(smRes.value);
        if (artRes.status === "fulfilled" && Array.isArray(artRes.value)) setArticles(artRes.value);
        if (qRes.status === "fulfilled" && Array.isArray(qRes.value)) setQuarantined(qRes.value);
        if (runsRes.status === "fulfilled" && Array.isArray(runsRes.value)) setRefreshRuns(runsRes.value);
        if (estRes.status === "fulfilled" && estRes.value) setIndexingEstimate(estRes.value);
        if (uSetRes.status === "fulfilled" && uSetRes.value) setUserSettings(uSetRes.value);
      } catch (err) {
        console.warn("Task 1 backend query warning:", err);
      }

      // 3. Task 2 Inbox Agent data
      try {
        const [interRes, lStatesRes, aSetRes, taxRes, gmRes, fbMetRes, fbHistRes] = await Promise.allSettled([
          api.listInteractions(),
          api.getLabelAutonomyStates(),
          api.getAutonomySettings(),
          api.getTaxonomy(),
          api.getGmailStatus(),
          api.getFeedbackMetrics(),
          api.getFeedbackHistory()
        ]);
        if (interRes.status === "fulfilled" && Array.isArray(interRes.value)) setInteractions(interRes.value);
        if (lStatesRes.status === "fulfilled" && lStatesRes.value?.labels) setLabelStates(lStatesRes.value.labels);
        if (aSetRes.status === "fulfilled" && aSetRes.value) setAutonomySettings(aSetRes.value);
        if (taxRes.status === "fulfilled" && Array.isArray(taxRes.value)) setTaxonomy(taxRes.value);
        if (gmRes.status === "fulfilled" && gmRes.value) setGmailStatus(gmRes.value);
        if (fbMetRes.status === "fulfilled" && fbMetRes.value) setFeedbackMetrics(fbMetRes.value);
        if (fbHistRes.status === "fulfilled" && Array.isArray(fbHistRes.value)) setFeedbackHistory(fbHistRes.value);
      } catch (err) {
        console.warn("Task 2 backend query warning:", err);
      }
    } catch (err) {
      console.error("Failed to load initial data:", err);
    }
  };

  useEffect(() => {
    loadData();

    const handleUnauthorized = () => {
      setUser(null);
      setIsAuthOpen(true);
    };

    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
    };
  }, []);

  // Handlers
  const handleToggleEmergencyStop = async () => {
    const nextVal = !autonomySettings.emergencyStop;
    try {
      const res = await api.toggleEmergencyStop(nextVal);
      setAutonomySettings((prev: any) => ({ ...prev, emergencyStop: res.emergencyStop }));
    } catch (err) {
      console.error("Failed to toggle emergency stop:", err);
    }
  };

  const handleSyncGmail = async () => {
    setIsSyncingGmail(true);
    try {
      const res = await api.syncGmail(20);
      await loadData();
    } catch (err) {
      console.error("Sync Gmail failed:", err);
    } finally {
      setIsSyncingGmail(false);
    }
  };

  const handleReview = async (
    interactionId: string,
    action: "APPROVE" | "EDIT" | "REJECT",
    finalReply?: string,
    notes?: string,
    sendViaGmail: boolean = false
  ) => {
    await api.submitReview(interactionId, action, user?.email || "specialist_ui", finalReply, notes, sendViaGmail);
    await loadData();
  };

  const handleSendViaGmail = async (interactionId: string) => {
    await api.sendApprovedEmailViaGmail(interactionId);
    await loadData();
  };

  const handleSimulateIncoming = async (email: CustomerEmail) => {
    await api.processEmail(email, "v2");
    await loadData();
    setCurrentView("inbox");
  };

  const handleRestoreQuarantined = async (articleId: string) => {
    await api.restoreQuarantinedArticle(articleId);
    await loadData();
  };

  const handleLogin = async (e: string, p: string) => {
    const res = await api.login(e, p);
    setUser(res.user);
    await loadData();
    return res.user;
  };

  const handleRegister = async (e: string, p: string) => {
    const res = await api.register(e, p);
    setUser(res.user);
    await loadData();
    return res.user;
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
  };

  const handleConnectRealGmail = async () => {
    try {
      const res = await api.getGmailAuthUrl();
      if (res.url) {
        window.open(res.url, "_blank", "width=600,height=700");
      }
    } catch (err: any) {
      alert(`OAuth Setup Notice: ${err.message}`);
    }
  };

  const handleConnectMockGmail = async () => {
    await api.connectMockGmail();
    const st = await api.getGmailStatus();
    setGmailStatus(st);
  };

  const handleDisconnectGmail = async () => {
    await api.disconnectGmail();
    const st = await api.getGmailStatus();
    setGmailStatus(st);
  };

  const handleToggleLabel = async (labelKey: string, disabled: boolean) => {
    await api.toggleLabelAutonomy(labelKey, disabled);
    const lStates = await api.getLabelAutonomyStates();
    setLabelStates(lStates.labels || []);
  };

  const handleSetThreshold = async (labelKey: string, threshold: number) => {
    await api.setLabelThreshold(labelKey, threshold);
    const lStates = await api.getLabelAutonomyStates();
    setLabelStates(lStates.labels || []);
  };

  const pendingCount = interactions.filter((i) => i.status === "PENDING_REVIEW").length;

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      {/* Top Navbar */}
      <Navbar
        user={user}
        gmailStatus={gmailStatus}
        emergencyStop={autonomySettings.emergencyStop}
        onToggleEmergencyStop={handleToggleEmergencyStop}
        onSyncGmail={handleSyncGmail}
        onOpenAuth={() => setIsAuthOpen(true)}
        onLogout={handleLogout}
        isSyncing={isSyncingGmail}
        searchQuery={globalSearch}
        onSearchChange={setGlobalSearch}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <Sidebar
          currentView={currentView}
          onSelectView={setCurrentView}
          pendingReviewCount={pendingCount}
          quarantinedCount={quarantined.length}
          onOpenCompose={() => setIsComposeOpen(true)}
        />

        {/* Main View Area */}
        <main className="flex-1 overflow-y-auto bg-slate-900/30">
          {currentView === "dashboard" && (
            <DashboardView
              articlesCount={articles.length}
              sitemapsCount={sitemaps.length}
              quarantinedCount={quarantined.length}
              interactionsCount={interactions.length}
              pendingReviewCount={pendingCount}
              labelStates={labelStates}
              sitemaps={sitemaps}
              onNavigate={setCurrentView}
            />
          )}

          {currentView === "inbox" && (
            <GmailInboxView
              interactions={interactions}
              onReview={handleReview}
              onSendViaGmail={handleSendViaGmail}
              onRefreshInbox={loadData}
              isGmailConnected={gmailStatus.isConnected}
            />
          )}

          {currentView === "reviews" && (
            <GmailInboxView
              interactions={interactions.filter((i) => i.status === "PENDING_REVIEW")}
              onReview={handleReview}
              onSendViaGmail={handleSendViaGmail}
              onRefreshInbox={loadData}
              isGmailConnected={gmailStatus.isConnected}
            />
          )}

          {currentView === "meeting_sow" && <MeetingToSOWView onRefreshData={loadData} />}

          {currentView === "chat" && <KnowledgeChatView onSendMessage={api.askQuestion} />}

          {currentView === "knowledge" && <KnowledgeBrainView articles={articles} />}

          {currentView === "sitemaps" && (
            <SitemapManagementView
              sitemaps={sitemaps}
              indexingEstimate={indexingEstimate}
              onPreview={api.previewSitemap}
              onCreateAndIndex={async (url, interval) => {
                const sm = await api.createSitemap(url, interval);
                await api.confirmIndexSitemap(sm.id);
                await loadData();
              }}
              onTriggerRefresh={async (id) => {
                await api.triggerRefreshRun(id);
                await loadData();
              }}
              onRefreshData={loadData}
            />
          )}

          {currentView === "refresh_runs" && (
            <RefreshRunsView runs={refreshRuns} onFetchRunDetails={api.getRefreshRunDetail} />
          )}

          {currentView === "quarantine" && (
            <QuarantineView
              quarantinedRecords={quarantined}
              onRestore={handleRestoreQuarantined}
              onRefreshData={loadData}
            />
          )}

          {currentView === "analytics" && (
            <AnalyticsView
              labelStates={labelStates}
              feedbackMetrics={feedbackMetrics}
              feedbackHistory={feedbackHistory}
              onToggleLabel={handleToggleLabel}
              onSetThreshold={handleSetThreshold}
            />
          )}

          {currentView === "ai_models" && <AIIntelligenceView />}

          {currentView === "settings" && (
            <SettingsView
              user={user}
              gmailStatus={gmailStatus}
              taxonomy={taxonomy}
              autonomySettings={autonomySettings}
              userSettings={userSettings}
              onUpdateAutonomySettings={async (set) => {
                const res = await api.updateAutonomySettings(set);
                setAutonomySettings(res);
              }}
              onUpdateUserSettings={async (set) => {
                const res = await api.updateUserSettings(set);
                setUserSettings(res);
              }}
              onUpdateTaxonomy={async (tax) => {
                const res = await api.updateTaxonomy(tax);
                setTaxonomy(res.taxonomy);
              }}
              onConnectRealGmail={handleConnectRealGmail}
              onConnectMockGmail={handleConnectMockGmail}
              onDisconnectGmail={handleDisconnectGmail}
              onLogout={handleLogout}
            />
          )}
        </main>
      </div>

      {/* Compose Email Modal */}
      <ComposeModal
        isOpen={isComposeOpen}
        onClose={() => setIsComposeOpen(false)}
        onSimulateIncoming={handleSimulateIncoming}
        onRefreshInbox={loadData}
        isGmailConnected={gmailStatus.isConnected}
      />

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
    </div>
  );
}

export default App;
