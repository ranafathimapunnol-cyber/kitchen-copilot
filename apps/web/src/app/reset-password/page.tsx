import type { Metadata } from "next";

import PasswordLinkForm from "@/components/auth/PasswordLinkForm";

export const metadata: Metadata = {
  title: "Reset your password · Kitchen Copilot",
  referrer: "no-referrer",
};

export default function ResetPasswordPage() {
  return <PasswordLinkForm purpose="reset" />;
}
