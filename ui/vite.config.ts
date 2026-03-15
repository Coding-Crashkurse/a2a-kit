import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    target: "es2020",
    minify: "esbuild",
  },
  server: {
    proxy: {
      "/.well-known": "http://localhost:8000",
      "/v1": "http://localhost:8000",
    },
  },
});
