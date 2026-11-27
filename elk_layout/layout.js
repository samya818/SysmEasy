const ELK = require("./node_modules/elkjs");

const chunks = [];
process.stdin.on("data", (c) => chunks.push(c));
process.stdin.on("end", async () => {
  try {
    const raw = Buffer.concat(chunks).toString("utf8");
    const graph = JSON.parse(raw);
    const elk = new ELK();
    const layouted = await elk.layout(graph);
    process.stdout.write(JSON.stringify(layouted));
  } catch (err) {
    process.stderr.write(String(err && err.stack ? err.stack : err));
    process.exit(1);
  }
});
