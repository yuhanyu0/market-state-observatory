import { useEffect, useRef } from "react";

const nodes = [
  { x: 0.12, y: 0.26, label: "DATA" },
  { x: 0.36, y: 0.16, label: "DIRECTION" },
  { x: 0.54, y: 0.46, label: "TRANSMISSION" },
  { x: 0.74, y: 0.2, label: "EPISODE" },
  { x: 0.88, y: 0.58, label: "CERTIFICATE" },
  { x: 0.3, y: 0.72, label: "CONFLICT" },
];

export function EvidenceGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const render = () => {
      const box = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(box.width * ratio));
      canvas.height = Math.max(1, Math.floor(box.height * ratio));
      context.scale(ratio, ratio);
      context.clearRect(0, 0, box.width, box.height);
      context.strokeStyle = "#a8adb4";
      context.lineWidth = 1;
      const links = [[0, 1], [0, 5], [1, 2], [5, 2], [2, 3], [2, 4], [3, 4]];
      links.forEach(([a, b]) => {
        context.beginPath();
        context.moveTo(nodes[a].x * box.width, nodes[a].y * box.height);
        context.lineTo(nodes[b].x * box.width, nodes[b].y * box.height);
        context.stroke();
      });
      nodes.forEach((node, index) => {
        const x = node.x * box.width;
        const y = node.y * box.height;
        context.fillStyle = index === 0 ? "#087f5b" : index === 4 ? "#1f2937" : "#fff";
        context.strokeStyle = "#1f2937";
        context.beginPath();
        context.arc(x, y, index === 0 || index === 4 ? 7 : 5, 0, Math.PI * 2);
        context.fill();
        context.stroke();
        context.fillStyle = "#4b5563";
        context.font = "600 10px system-ui";
        context.fillText(node.label, x + 11, y + 4);
      });
    };
    render();
    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  return <canvas ref={canvasRef} className="evidence-graph" aria-label="Evidence lineage from data to certificate" />;
}
