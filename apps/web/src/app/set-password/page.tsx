import type { Metadata } from "next";

import PasswordLinkForm from "@/components/auth/PasswordLinkForm";

export const metadata: Metadata = {
  title: "Set your password · Kitchen Copilot",
  referrer: "no-referrer",
};

export default function SetPasswordPage() {
  return <PasswordLinkForm purpose="setup" />;
}
