"use client";

import { useRef, useState } from "react";
import { ImageOff, ImagePlus, Trash2, Upload } from "lucide-react";

import { api, apiRequest, apiUrl } from "@/lib/api/client";
import { errorMessage } from "@/lib/payments";
import { MEDIA_SPECS, PLATFORM_API, mediaPath, type CampusMedia } from "@/lib/platform";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { Section } from "./parts";

type Kind = "logo" | "photo";

/** Upload, replace and remove a campus's logo and photo (platform only). */
export default function CampusMediaSection({ campusId, campusName, media, onChange }: {
  campusId: number; campusName: string; media: CampusMedia | undefined; onChange: () => void;
}) {
  const toast = useToast();
  const inputs = { logo: useRef<HTMLInputElement>(null), photo: useRef<HTMLInputElement>(null) };
  const [busy, setBusy] = useState<Kind | null>(null);
  const [removing, setRemoving] = useState<Kind | null>(null);

  if (!media?.available) {
    return (
      <Section title="Logo and photo">
        <p className="px-5 py-4 text-sm text-slate-600">Campus logos and photos become available once database migration e2b7c4d9a5f1 is applied.</p>
      </Section>
    );
  }

  async function upload(kind: Kind, file: File | undefined) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error("The image is larger than 5 MB."); return; }
    setBusy(kind);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiRequest(`${PLATFORM_API}/campuses/${campusId}/media/${kind}`, { method: "PUT", body: form });
      toast.success(`${MEDIA_SPECS[kind].label} saved.`);
      onChange();
    } catch (err) {
      toast.error(errorMessage(err, "The image could not be saved."));
    } finally {
      setBusy(null);
      if (inputs[kind].current) inputs[kind].current.value = "";
    }
  }

  async function remove() {
    if (!removing) return;
    const kind = removing;
    setBusy(kind);
    try {
      await api.delete(`${PLATFORM_API}/campuses/${campusId}/media/${kind}`);
      toast.success(`${MEDIA_SPECS[kind].label} removed.`);
      setRemoving(null);
      onChange();
    } catch (err) {
      toast.error(errorMessage(err, "The image could not be removed."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Section title="Logo and photo" description="Shown on the platform; the logo also appears in this campus's own app.">
      <div className="grid gap-5 px-5 py-4 sm:grid-cols-[auto_minmax(0,1fr)]" data-campus-media>
        {(["logo", "photo"] as const).map((kind) => {
          const version = media[kind];
          return (
            <div key={kind} className="contents">
              <div className={cn("flex shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-slate-200 bg-slate-100",
                kind === "logo" ? "h-24 w-24" : "h-24 w-40")} data-media-preview={kind}>
                {version
                  ? /* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */
                    <img onError={(e) => { e.currentTarget.hidden = true; }} src={apiUrl(mediaPath(campusId, kind, version))} alt={`${campusName} ${MEDIA_SPECS[kind].label.toLowerCase()}`}
                      className={kind === "logo" ? "h-full w-full object-contain p-2" : "h-full w-full object-cover"} />
                  : <ImageOff size={22} aria-hidden className="text-slate-400" />}
              </div>
              <div className="min-w-0 space-y-2">
                <p className="text-sm font-semibold text-slate-900">{MEDIA_SPECS[kind].label}</p>
                <p className="text-xs text-slate-500">{MEDIA_SPECS[kind].hint}</p>
                <input ref={inputs[kind]} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only"
                  aria-label={`Choose ${MEDIA_SPECS[kind].label.toLowerCase()} file`} data-media-input={kind}
                  onChange={(e) => void upload(kind, e.target.files?.[0])} />
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" loading={busy === kind && !removing}
                    icon={version ? <Upload size={14} /> : <ImagePlus size={14} />} onClick={() => inputs[kind].current?.click()}>
                    {version ? "Replace" : `Add ${kind}`}
                  </Button>
                  {version && <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => setRemoving(kind)}>Remove</Button>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <Modal open={removing !== null} onClose={() => busy === null && setRemoving(null)} size="sm"
        title={`Remove the ${removing ? MEDIA_SPECS[removing].label.toLowerCase() : ""}?`}
        description="The image is deleted from storage. You can add a new one at any time."
        footer={<><Button variant="secondary" onClick={() => setRemoving(null)} disabled={busy !== null}>Cancel</Button>
          <Button variant="danger" loading={busy !== null} onClick={remove}>Remove</Button></>}>
        <span />
      </Modal>
    </Section>
  );
}
