#!/usr/bin/env node
const args = process.argv.slice(2).reduce((acc, arg, i, arr) => {
  if (arg.startsWith("--")) {
    const key = arg.slice(2).toLowerCase();
    const next = arr[i + 1];
    acc[key] = next && !next.startsWith("--") ? next : true;
  }
  return acc;
}, {});

const {
  mvp,
  waitlist = 0,
  lois = 0,         // Letters of Intent
  paying = 0,
  mrr = 0,
  revenue = 0,
  team = 1,
  metrics = ""
} = args;

const productScore = mvp === "true" ? 25 : 0;
const tractionScore = Math.min(25,
  (Number(waitlist) * 0.1) +   // Waitlist: low weight
  (Number(lois) * 0.5) +       // LOIs: medium weight
  (Number(paying) * 1.0) +     // Paying: highest weight
  (Number(mrr) * 0.05)         // MRR: strong signal
);
const revenueScore = Math.min(25, Math.floor(Math.log10(Number(revenue) || Number(mrr) * 12 + 1) * 4));
const teamScore = Math.min(15, Number(team) * 5);
const narrativeScore = metrics ? 10 : 0;

const categories = [
  { label: "Product", score: productScore, max: 25 },
  { label: "Traction", score: Math.round(tractionScore), max: 25 },
  { label: "Revenue", score: revenueScore, max: 25 },
  { label: "Team", score: teamScore, max: 15 },
  { label: "Metrics Narrative", score: narrativeScore, max: 10 },
];

const total = categories.reduce((sum, c) => sum + c.score, 0);
const max = categories.reduce((sum, c) => sum + c.max, 0);

console.log("\n=== Fundraising Readiness Calculator ===\n");
categories.forEach((c) => {
  const pct = c.score / c.max;
  const bar = "█".repeat(Math.floor(pct * 5)) + "░".repeat(5 - Math.floor(pct * 5));
  console.log(`  ${c.label.padEnd(20)} [${bar}] ${c.score}/${c.max}`);
});
console.log(`\n  SCORE: ${total}/${max}`);
console.log(`  ${total >= 60 ? "READY — start approaching investors." : total >= 35 ? "ALMOST — strengthen weak areas." : "NOT YET — validate further first."}`);
console.log("\n  Traction weights: paying customers > LOIs > waitlist > MRR growth\n");