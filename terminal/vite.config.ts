import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// base: "./" → derlenmiş çıktı herhangi bir alt dizinden (ör. dahili sunucu) servis edilebilir.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
});
