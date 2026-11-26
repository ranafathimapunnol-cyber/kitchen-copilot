"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CookingPot } from "lucide-react";

import IssueForm from "@/components/kitchen/IssueForm";
import PageHeader from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";

export default function NewKitchenIssuePage() {
  const router = useRouter();
  const toast = useToast();

  return (
    <div className="space-y-6 pb-6">
      <Link href="/dashboard/kitchen-issues" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft size={15} aria-hidden />
        Kitchen issues
      </Link>
      <PageHeader
        eyebrow="Operations"
        icon={CookingPot}
        title="New kitchen issue"
        description="Record the ingredients the store issues to the kitchen for one meal session and menu. You are recorded as the responsible user."
      />
      <IssueForm
        onCancel={() => router.push("/dashboard/kitchen-issues")}
        onSaved={(issue) => {
          toast.success(`Draft ${issue.issue_number} saved. Confirm it to take the stock out.`);
          router.push(`/dashboard/kitchen-issues/${issue.id}`);
        }}
      />
    </div>
  );
}
