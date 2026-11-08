import { useEffect } from "react";
import { pageSeo, PRODUCT_SCHEMA, PUBLIC_URL } from "../utils/seo";

export function usePageSeo(route, role, activePage) {
  useEffect(() => {
    const seo = pageSeo(route, role, activePage);
    document.title = seo.title;
    function meta(attribute, key, content) {
      let element = document.head.querySelector(`meta[${attribute}="${key}"]`);
      if (!element) { element = document.createElement("meta"); element.setAttribute(attribute, key); document.head.appendChild(element); }
      element.setAttribute("content", content);
    }
    meta("name", "description", seo.description);
    meta("name", "robots", seo.indexable ? "index,follow" : "noindex,nofollow,noarchive");
    meta("property", "og:title", seo.title);
    meta("property", "og:description", seo.description);
    meta("name", "twitter:title", seo.title);
    meta("name", "twitter:description", seo.description);
    let canonical = document.head.querySelector('link[rel="canonical"]');
    let schema = document.getElementById("product-schema");
    if (seo.indexable) {
      if (!canonical) { canonical = document.createElement("link"); canonical.rel = "canonical"; document.head.appendChild(canonical); }
      canonical.href = PUBLIC_URL;
      meta("property", "og:url", PUBLIC_URL);
      if (!schema) { schema = document.createElement("script"); schema.id = "product-schema"; schema.type = "application/ld+json"; document.head.appendChild(schema); }
      schema.textContent = JSON.stringify(PRODUCT_SCHEMA);
    } else {
      canonical?.remove();
      schema?.remove();
      document.head.querySelector('meta[property="og:url"]')?.remove();
    }
  }, [route, role, activePage]);
}
