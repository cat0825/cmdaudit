import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/**
 * 产物必须是**单个** HTML：Python 侧只做一次字符串注入，
 * 双击 file:// 即可打开，不允许出现任何外链资源（含字体、CDN、sourcemap）。
 */
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    target: "es2022",
    outDir: "dist",
    assetsInlineLimit: 100 * 1024 * 1024, // 字体/图标一律内联
    cssCodeSplit: false,
    sourcemap: false,
    reportCompressedSize: false,
    chunkSizeWarningLimit: 4096,
  },
});
