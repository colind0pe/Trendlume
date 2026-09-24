"use client";

import { useEffect, useRef, useState } from "react";

export const TASK_LIFECYCLE_EVENTS = new Set([
  "task.started",
  "task.completed",
  "task.failed",
  "task.cancelled",
]);

export const JOB_LIFECYCLE_EVENTS = new Set([
  "job.started",
  "job.retrying",
  "job.completed",
  "job.failed",
  "job.cancelled",
  "job.uncertain",
]);

export const TASK_REFRESH_EVENTS = new Set([
  ...TASK_LIFECYCLE_EVENTS,
  ...JOB_LIFECYCLE_EVENTS,
  "step.started",
  "step.completed",
  "scene.status_changed",
  "asset.created",
  "video.preview_ready",
]);

export const TASK_EVENT_NAMES = [
  ...TASK_REFRESH_EVENTS,
  "step.failed",
  "step.reused",
  "step.retrying",
  "step.interrupted",
  "step.cancelled",
  "research.warning",
  "publish.verification_needed",
];

export interface TaskEventData {
  task_id?: string;
  job_id?: string;
  step_run_id?: string;
  unit_key?: string;
  attempt?: number;
  artifact_ids?: string[];
  stage?: string;
  status?: string;
  progress?: number;
  message?: string;
  current_scene?: number;
  total_scenes?: number;
  scene_id?: string;
  scene_index?: number;
  asset_id?: string;
  asset_type?: string;
  preview_url?: string;
  final_video_url?: string;
  result?: any;
  [key: string]: any;
}

export interface TaskEvent {
  event: string;
  data: TaskEventData;
  event_id?: number | string | null;
  created_at: string;
}

export interface UseTaskEventsOptions {
  taskId?: string;
  enabled?: boolean;
  onEvent?: (event: TaskEvent) => void;
  onReconnect?: () => void;
}

const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30000;

export function useTaskEvents({
  taskId,
  enabled = true,
  onEvent,
  onReconnect,
}: UseTaskEventsOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const lastEventIdRef = useRef<string>("");
  const lastNumericEventIdRef = useRef<number | null>(null);

  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onReconnectRef = useRef(onReconnect);
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    lastEventIdRef.current = "";
    lastNumericEventIdRef.current = null;
    setIsConnected(false);

    if (!enabled) return undefined;

    let disposed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempts = 0;
    let hasConnected = false;
    const seenEvents = new Set<string>();

    const endpoint = taskId
      ? `/api/v1/tasks/${encodeURIComponent(taskId)}/events`
      : "/api/v1/events/stream";

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== null) return;
      reconnectAttempts += 1;
      const delay = Math.min(
        MAX_RECONNECT_MS,
        BASE_RECONNECT_MS * 2 ** Math.min(reconnectAttempts - 1, 5)
      );
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    function connect() {
      if (disposed) return;
      const lastEventId = lastEventIdRef.current;
      const url =
        taskId && lastEventId
          ? `${endpoint}?last_event_id=${encodeURIComponent(lastEventId)}`
          : endpoint;
      const currentSource = new EventSource(url);
      source = currentSource;

      currentSource.onopen = () => {
        setIsConnected(true);
        if (hasConnected) onReconnectRef.current?.();
        hasConnected = true;
        reconnectAttempts = 0;
      };

      const handleMessage = (event: MessageEvent, eventType: string) => {
        try {
          const parsed = JSON.parse(event.data);
          const payload =
            parsed?.data && typeof parsed.data === "object" ? parsed.data : parsed;
          const actualEvent = parsed?.event || eventType;
          const eventId = (parsed?.event_id ?? event.lastEventId) || null;
          const createdAt = parsed?.created_at || new Date().toISOString();
          const numericEventId = eventId !== null && eventId !== "" ? Number(eventId) : NaN;

          if (Number.isFinite(numericEventId)) {
            if (
              lastNumericEventIdRef.current !== null &&
              numericEventId <= lastNumericEventIdRef.current
            ) {
              return;
            }
            lastNumericEventIdRef.current = numericEventId;
            lastEventIdRef.current = String(eventId);
          }

          const key = `${actualEvent}|${eventId ?? ""}|${createdAt}|${payload?.task_id ?? ""}|${payload?.job_id ?? ""}`;
          if (seenEvents.has(key)) return;
          seenEvents.add(key);
          if (seenEvents.size > 500) {
            const oldest = seenEvents.values().next().value;
            if (oldest) seenEvents.delete(oldest);
          }

          const taskEvent: TaskEvent = {
            event: actualEvent,
            data: payload || {},
            event_id: eventId,
            created_at: createdAt,
          };
          onEventRef.current?.(taskEvent);
        } catch (error) {
          console.error("Failed to parse SSE event:", error);
        }
      };

      TASK_EVENT_NAMES.forEach((name) => {
        currentSource.addEventListener(name, (event) =>
          handleMessage(event as MessageEvent, name)
        );
      });

      currentSource.onerror = () => {
        if (source !== currentSource) return;
        currentSource.close();
        source = null;
        setIsConnected(false);
        scheduleReconnect();
      };
    }

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      source?.close();
      source = null;
      setIsConnected(false);
    };
  }, [enabled, taskId]);

  return { isConnected };
}
