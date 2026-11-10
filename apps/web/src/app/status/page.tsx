"use client";

import { useEffect, useState } from "react";

export default function StatusPage() {
  const [apiStatus, setApiStatus] = useState("Checking...");
  const [lastChecked, setLastChecked] = useState("");

  useEffect(() => {
    async function checkApi() {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/health`, {
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("API unavailable");
        }

        setApiStatus("Operational");
      } catch {
        setApiStatus("Unavailable");
      }

      setLastChecked(new Date().toLocaleString());
    }

    checkApi();
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 p-8 text-slate-900">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-bold">Kitchen Copilot Status</h1>

        <p className="mt-2 text-slate-600">
          Service availability overview
        </p>

        <div className="mt-8 rounded-xl border bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium">Frontend</span>
            <span className="text-green-600">Operational</span>
          </div>

          <div className="mt-5 flex items-center justify-between">
            <span className="font-medium">Backend API</span>
            <span
              className={
                apiStatus === "Operational"
                  ? "text-green-600"
                  : apiStatus === "Unavailable"
                    ? "text-red-600"
                    : "text-slate-500"
              }
            >
              {apiStatus}
            </span>
          </div>

          <p className="mt-6 text-sm text-slate-500">
            Last checked: {lastChecked || "Checking..."}
          </p>

          <button
            onClick={() => window.location.reload()}
            className="mt-5 rounded-lg bg-blue-700 px-4 py-2 text-white"
          >
            Check again
          </button>
        </div>
      </div>
    </main>
  );
}