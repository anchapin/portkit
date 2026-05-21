#!/usr/bin/env node
import readline from "readline";

const FIELDS = [
  { key: "problem", label: "Top 3 Problems", placeholder: "e.g., Eating healthy is time-consuming, Meal planning is tedious, Food waste is high" },
  { key: "customer", label: "Target Customer", placeholder: "e.g., Busy professionals aged 25-40, dual-income households" },
  { key: "solution", label: "Solution (Top 3 Features)", placeholder: "e.g., AI-powered personalized meal plans, One-click grocery lists, Waste tracking" },
  { key: "uniques", label: "Unique Value Proposition", placeholder: "e.g., Healthy eating made effortless — save 2hrs/week" },
  { key: "unfair", label: "Unfair Advantage", placeholder: "e.g., Proprietary nutritional database, Influencer partnerships" },
  { key: "channels", label: "Distribution Channels", placeholder: "e.g., TikTok, Instagram, SEO, Paid ads" },
  { key: "metrics", label: "Key Metrics", placeholder: "e.g., MAU, conversion rate, LTV, CAC" },
  { key: "cost", label: "Cost Structure", placeholder: "e.g., App dev, AI infra, Marketing, Support" },
  { key: "revenue", label: "Revenue Streams", placeholder: "e.g., Subscription $9.99/mo, Affiliate, White-label" },
];

const args = process.argv.slice(2).reduce((acc, arg, i, arr) => {
  if (arg.startsWith("--")) {
    const key = arg.slice(2).toLowerCase();
    const next = arr[i + 1];
    acc[key] = next && !next.startsWith("--") ? next : true;
  }
  return acc;
}, {});

function askField(rl, field) {
  return new Promise((resolve) => {
    rl.question(`\n  ${field.label}\n  (${field.placeholder})\n  > `, (answer) => resolve(answer));
  });
}

async function run() {
  console.log("\n=== Lean Canvas Generator ===\n");

  const canvas = {};
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  for (const field of FIELDS) {
    const key = field.key === "uniques" ? "uniques" : field.key;
    canvas[field.key] = args[key] || await askField(rl, field);
  }
  rl.close();

  console.log("\n\n=== YOUR LEAN CANVAS ===\n");
  const col = (label, content) => `| ${label.padEnd(22)} | ${(content || "").padEnd(50)}`;
  console.log(col("FIELD", "CONTENT"));
  console.log("-".repeat(78));
  FIELDS.forEach((f) => console.log(col(f.label, canvas[f.key])));
  console.log("");
}

run().catch(console.error);