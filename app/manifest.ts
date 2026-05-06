import type { MetadataRoute } from "next"
import { getAssetUrl } from "@/lib/base-path"
export default function manifest(): MetadataRoute.Manifest {
    return {
        name: "openBIMForge",
        short_name: "openBIMForge",
        description:
            "Generative reasoning in multi-agent interactive BIM formation. Create BIM concepts, Vectorworks handoffs, VWX files, and IFC artifacts with AI assistance.",
        start_url: getAssetUrl("/"),
        display: "standalone",
        background_color: "#f9fafb",
        theme_color: "#171d26",
        icons: [
            {
                src: getAssetUrl("/favicon-192x192.png"),
                sizes: "192x192",
                type: "image/png",
                purpose: "any",
            },
            {
                src: getAssetUrl("/favicon-512x512.png"),
                sizes: "512x512",
                type: "image/png",
                purpose: "any",
            },
        ],
    }
}
