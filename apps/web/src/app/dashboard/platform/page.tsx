import { redirect } from "next/navigation";

/** The platform moved to its own app with its own sign-in (/platform). */
export default function OldPlatformPage() {
  redirect("/platform");
}
