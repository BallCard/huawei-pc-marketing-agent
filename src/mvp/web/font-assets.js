(function () {
  "use strict";
  const cached = new Map();
  function dataUrl(url) {
    if (!cached.has(url)) cached.set(url, fetch(url).then(async response => {
      if (!response.ok) throw new Error(`Font download failed: ${response.status}`);
      const blob = new Blob([await response.arrayBuffer()],{type:"font/woff2"});
      return new Promise((resolve,reject)=>{
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      });
    }).catch(error=>{cached.delete(url);throw error;}));
    return cached.get(url);
  }
  function intersects(range,points) {
    if (!range) return true;
    return range.split(",").some(part=>{
      const token=part.trim().replace(/^U\+/i,"");
      const [first,last]=token.includes("?") ? [token.replace(/\?/g,"0"),token.replace(/\?/g,"f")] : token.split("-");
      const start=parseInt(first,16),end=parseInt(last || first,16);
      return points.some(point=>point>=start && point<=end);
    });
  }
  async function exportStyles(preview) {
    const points=[...new Set([...preview.textContent].map(c=>c.codePointAt(0)))];
    const families=new Set([preview,...preview.querySelectorAll("*")].flatMap(node=>getComputedStyle(node).fontFamily.split(",").map(s=>s.trim().replace(/["']/g,""))));
    const licenses=new Set(),rules=[];
    for (const sheet of document.styleSheets) {
      for (const rule of sheet.cssRules || []) {
        if (rule.type !== CSSRule.FONT_FACE_RULE) { rules.push(Promise.resolve(rule.cssText));continue; }
        const family=rule.style.getPropertyValue("font-family").replace(/["']/g,"").trim();
        if (!families.has(family) || !intersects(rule.style.getPropertyValue("unicode-range"),points)) continue;
        const match=rule.style.getPropertyValue("src").match(/url\(["']?([^"')]+)["']?\)/);
        if (!match) continue;
        const url=new URL(match[1],sheet.href || document.baseURI);
        const packageName=url.pathname.match(/\/fonts\/([^/]+)\//)?.[1];
        if (packageName) licenses.add(packageName);
        rules.push(dataUrl(url.href).then(data=>rule.cssText.replace(/url\(["']?[^"')]+["']?\)/,`url("${data}")`)));
      }
    }
    const licenseText=await Promise.all([...licenses].map(async name=>{
      const response=await fetch(`/static/fonts/${name}/OFL.txt`);
      if (!response.ok) throw new Error("Font license could not be included");
      return `/* ${name} — SIL Open Font License\n${(await response.text()).replace(/\*\//g,"* /")}\n*/`;
    }));
    return [...licenseText,...await Promise.all(rules)].join("\n");
  }
  window.FontAssets={exportStyles};
})();
