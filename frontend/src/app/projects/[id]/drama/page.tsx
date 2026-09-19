"use client";

import { useParams } from "next/navigation";

import { DramaWorkspace } from "@/components/drama/drama-workspace";

export default function ProjectDramaPage() {
  const params = useParams<{ id: string }>();
  return <DramaWorkspace projectId={params.id} />;
}
