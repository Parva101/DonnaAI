/**
 * Socket.IO client singleton + lifecycle hook.
 */

import { useEffect } from "react";
import { io, Socket } from "socket.io-client";

import { useAuthStore } from "@/stores/authStore";

const WS_URL = import.meta.env.VITE_WS_URL ?? "http://localhost:8010";

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
 * Connect when user is authenticated and join user room for targeted events.
 */
export function useSocket() {
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    const s = getSocket();

    if (!user?.id) {
      if (s.connected) {
        s.disconnect();
      }
      return;
    }

    if (!s.connected) {
      s.connect();
    }
    s.emit("join", { user_id: user.id });

    return () => {
      s.emit("leave", { user_id: user.id });
    };
  }, [user?.id]);

  return getSocket();
}
