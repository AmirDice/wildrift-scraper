import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/" },
      // Block AI training / answer-engine crawlers from scraping the data.
      {
        userAgent: [
          "GPTBot",
          "ChatGPT-User",
          "OAI-SearchBot",
          "ClaudeBot",
          "Claude-Web",
          "anthropic-ai",
          "Google-Extended",
          "PerplexityBot",
          "CCBot",
          "Bytespider",
          "Amazonbot",
          "meta-externalagent",
        ],
        disallow: "/",
      },
    ],
    sitemap: "https://wrtruemeta.com/sitemap.xml",
  };
}
