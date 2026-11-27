"use client";

import { useEffect, useState } from "react";

import { api, apiUrl } from "@/lib/api/client";

type Media = { logo: string | null; photo: string | null; available: boolean };

/** The signed-in user's own campus logo/photo URLs (null when not set). */
export function useCampusMedia(): { logo: string | null; photo: string | null } {
  const [media, setMedia] = useState<Media | null>(null);
  useEffect(() => {
    let active = true;
    api.get<Media>("/api/campus-media").then((m) => active && setMedia(m)).catch(() => undefined);
    return () => { active = false; };
  }, []);
  return {
    logo: media?.logo ? apiUrl(`/api/campus-media/logo?v=${media.logo}`) : null,
    photo: media?.photo ? apiUrl(`/api/campus-media/photo?v=${media.photo}`) : null,
  };
}
