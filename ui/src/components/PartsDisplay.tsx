import type { Part } from "../lib/types";

export function PartsDisplay({ parts }: { parts: Part[] }) {
  return (
    <>
      {parts.map((p, i) => {
        if (p.kind === "text" && p.text) {
          return <div key={i} className="artifact-text">{p.text}</div>;
        }
        if (p.kind === "data") {
          return <pre key={i} className="json-block">{JSON.stringify(p.data, null, 2)}</pre>;
        }
        if (p.kind === "file") {
          return (
            <div key={i} style={{ color: "var(--text-dim)", fontSize: 12 }}>
              [file: {p.filename || p.mediaType || "binary"}]
            </div>
          );
        }
        return null;
      })}
    </>
  );
}
