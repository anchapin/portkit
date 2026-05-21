#!/usr/bin/env node
import readline from "readline";

const DIMENSIONS = [
  { name: "Problem Clarity", weight: 1.5, questions: ["Can you describe the problem in one sentence?", "How widespread is this problem?"] },
  { name: "Market Size", weight: 1.2, questions: ["Estimated TAM ($)?", "Served Available Market (SAM)?", "Serviceable Obtainable Market (SOM)?"] },
  { name: "Competition", weight: 1.0, questions: ["Who solves this today?", "What's their weakness?"] },
  { name: "Defensibility", weight: 1.3, questions: ["Network effects?", "Proprietary data?", "Brand?"] },
  { name: "Revenue Model", weight: 1.4, questions: ["How will you charge?", "Willingness to pay validated?"] },
  { name: "Scalability", weight: 1.1, questions: ["Can you grow without proportional headcount?", "Margin expansion over time?"] },
  { name: "Execution Risk", weight: 1.0, questions: ["Technical feasibility?", "Team capability match?"] },
  { name: "Passion & Commitment", weight: 1.2, questions: ["Why you? Why now?"] },
];

function askQuestion(rl, question) {
  return new Promise((resolve) => {
    rl.question(`  ${question} `, (answer) => resolve(answer));
  });
}

function scoreDimension(answers) {
  const text = answers.join(" ").toLowerCase();
  let score = 7;
  const reasons = [];

  if (text.includes("validated") || text.includes("tested") || text.includes("proven")) {
    score += 1;
    reasons.push("+1: validation evidence detected");
  }
  if (text.includes("don't know") || text.includes("unsure") || text.includes("not sure")) {
    score -= 2;
    reasons.push("-2: uncertainty detected");
  }
  if (text.includes("maybe") || text.includes("possibly")) {
    score -= 1;
    reasons.push("-1: hedging language detected");
  }
  if (text.includes("big") || text.includes("large") || text.includes("massive")) {
    score += 0.5;
    reasons.push("+0.5: positive market language");
  }
  if (text.includes("no ") && !text.includes("not ") && !text.includes("no existing")) {
    score -= 1;
    reasons.push("-1: negative language detected");
  }

  return {
    score: Math.max(1, Math.min(10, score)),
    reasons: reasons.length ? reasons : ["default (no strong signals)"]
  };
}

async function run() {
  console.log("\n=== Idea Validator ===\n");
  const idea = process.argv[2] || (await new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question("Describe your business idea: ", (answer) => { rl.close(); resolve(answer); });
  }));

  if (!idea) { console.log("No idea provided."); process.exit(1); }

  console.log(`\nEvaluating: "${idea}"\n`);
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const results = [];
  let total = 0;
  let totalWeight = 0;

  for (const dim of DIMENSIONS) {
    console.log(`\n--- ${dim.name} (weight: ${dim.weight}) ---`);
    const answers = [];
    for (const q of dim.questions) {
      const answer = await askQuestion(rl, q);
      answers.push(answer);
    }
    const { score, reasons } = scoreDimension(answers);
    results.push({ name: dim.name, score, weight: dim.weight, answers, reasons });
    total += score * dim.weight;
    totalWeight += dim.weight;
    console.log(`  Score: ${score}/10 | ${reasons.join(", ")}`);
  }
  rl.close();

  const final = (total / totalWeight).toFixed(1);
  console.log("\n=== Results ===\n");
  results.forEach((r) => console.log(`  ${r.name}: ${r.score}/10`));
  console.log(`\n  WEIGHTED SCORE: ${final}/10`);
  console.log(`  ${final >= 8 ? "STRONG — proceed with detailed planning." : final >= 6 ? "PROMISING — address weak areas before scaling." : "REVISIT — refine the core hypothesis."}`);
  console.log("");
}

run().catch(console.error);