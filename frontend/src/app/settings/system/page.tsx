"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/auth/clerk";
import { AlertTriangle, GitBranch, RefreshCw, Server } from "lucide-react";

import { customFetch } from "@/api/mutator";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";

interface SystemInfo {
  current_branch: string;
  commit_sha: string;
  remote_branches: string[];
  self_update_available: boolean;
}

interface BranchSwitchResult {
  status: string;
  message: string;
}

type FetchResult<T> = { data: T; status: number };

export default function SystemSettingsPage() {
  const { isSignedIn } = useAuth();

  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedBranch, setSelectedBranch] = useState("");
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const [switchSuccess, setSwitchSuccess] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const fetchInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await customFetch<FetchResult<SystemInfo>>(
        "/api/v1/system/info",
        { method: "GET" },
      );
      setInfo(res.data);
      if (res.data.current_branch && !selectedBranch) {
        setSelectedBranch(res.data.current_branch);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load system info",
      );
    } finally {
      setLoading(false);
    }
  }, [selectedBranch]);

  useEffect(() => {
    if (isSignedIn) {
      fetchInfo();
    }
  }, [isSignedIn, fetchInfo]);

  const handleSwitch = async () => {
    if (!selectedBranch || selectedBranch === info?.current_branch) return;
    setSwitching(true);
    setSwitchError(null);
    setSwitchSuccess(null);
    try {
      const res = await customFetch<FetchResult<BranchSwitchResult>>(
        "/api/v1/system/switch-branch",
        {
          method: "POST",
          body: JSON.stringify({ branch: selectedBranch }),
        },
      );
      setSwitchSuccess(res.data.message);
    } catch (err) {
      setSwitchError(
        err instanceof Error ? err.message : "Branch switch failed",
      );
    } finally {
      setSwitching(false);
    }
  };

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view system settings.",
        forceRedirectUrl: "/settings/system",
        signUpForceRedirectUrl: "/settings/system",
      }}
      title="System"
      description="View system status and switch branches."
    >
      <div className="space-y-6">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
            <Server className="h-4 w-4 text-slate-500" />
            System Info
          </h2>

          {loading ? (
            <p className="mt-4 text-sm text-slate-500">Loading...</p>
          ) : error ? (
            <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {error}
            </div>
          ) : info ? (
            <div className="mt-4 space-y-3">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <GitBranch className="h-4 w-4 text-slate-500" />
                    Current Branch
                  </label>
                  <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900">
                    {info.current_branch}
                  </p>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">
                    Commit SHA
                  </label>
                  <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-600">
                    {info.commit_sha.slice(0, 12)}
                  </p>
                </div>
              </div>

              {!info.self_update_available ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  <AlertTriangle className="mr-1 inline h-4 w-4" />
                  Self-update is not available. The repo and Docker socket must
                  be mounted for branch switching.
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        {info?.self_update_available ? (
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
              <GitBranch className="h-4 w-4 text-slate-500" />
              Switch Branch
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Select a branch to switch to. The app will rebuild and restart.
            </p>

            <div className="mt-4 flex items-end gap-3">
              <div className="flex-1 space-y-2">
                <label className="text-sm font-medium text-slate-700">
                  Target Branch
                </label>
                <select
                  value={selectedBranch}
                  onChange={(e) => setSelectedBranch(e.target.value)}
                  disabled={switching}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                >
                  {info.remote_branches.map((branch) => (
                    <option key={branch} value={branch}>
                      {branch}
                      {branch === info.current_branch ? " (current)" : ""}
                    </option>
                  ))}
                </select>
              </div>

              <Button
                onClick={() => {
                  setSwitchError(null);
                  setSwitchSuccess(null);
                  setConfirmOpen(true);
                }}
                disabled={
                  switching || selectedBranch === info.current_branch
                }
              >
                <RefreshCw
                  className={`h-4 w-4 ${switching ? "animate-spin" : ""}`}
                />
                {switching ? "Switching..." : "Switch & Rebuild"}
              </Button>

              <Button
                variant="outline"
                onClick={fetchInfo}
                disabled={loading}
              >
                <RefreshCw
                  className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
                />
                Refresh
              </Button>
            </div>

            {switchError ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {switchError}
              </div>
            ) : null}
            {switchSuccess ? (
              <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                {switchSuccess}
              </div>
            ) : null}
          </section>
        ) : null}
      </div>

      <ConfirmActionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Switch branch and rebuild?"
        description={`This will switch to branch "${selectedBranch}" and trigger a Docker Compose rebuild. The app will be temporarily unavailable during the rebuild.`}
        onConfirm={handleSwitch}
        isConfirming={switching}
        errorMessage={switchError}
        confirmLabel="Switch & Rebuild"
        confirmingLabel="Switching..."
        ariaLabel="Branch switch confirmation"
      />
    </DashboardPageLayout>
  );
}
