/**
 * Socket.IO client — provides a singleton socket instance and a React hook.
 *
 * The socket connects to the backend WebSocket server mounted at /ws.
 * It auto-connects when the user is authenticated and disconnects on logout.
 */

import { useEffect, useRef } from "react";
import { io, Socket } from "socket.io-client";
import { useAuthStore } from "@/stores/authStore";

const WS_URL = import.meta.env.VITE_WS_URL ?? "http://localhost:8000";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io(WS_URL, {
      path: "/ws/socket.io",
      autoConnect: false,
      withCredentials: true,
      transports: ["websocket", "polling"],
    });
  }
  return socket;
}

/**
 * Hook that manages socket lifecycle based on auth state.
 * Call once at the app shell level.
 *
 * Currently disabled — WebSockets will be activated in Phase 3
 * when real-time messaging (Slack, WhatsApp, Teams) needs instant push.
 */
export function useSocket() {
  // No-op for now — re-enable when we need real-time push
  return null;
}
