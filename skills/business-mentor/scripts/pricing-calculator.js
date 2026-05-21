#!/usr/bin/env node
const args = process.argv.slice(2).reduce((acc, arg, i, arr) => {
  if (arg.startsWith("--")) {
    const key = arg.slice(2).toLowerCase();
    const next = arr[i + 1];
    acc[key] = next && !next.startsWith("--") ? parseFloat(next) : true;
  }
  return acc;
}, {});

const { cost = 0, competitorprice = 0, valuedelivered = 0, capturerate = 0.15 } = args;

const captureRate = Number(capturerate);
if (captureRate < 0.05 || captureRate > 0.5) {
  console.error("Capture rate must be between 0.05 (5%) and 0.50 (50%)");
  process.exit(1);
}

const floor = Number(cost) * 1.3;
const competitive = Number(competitorprice) || floor * 1.5;
const value = Number(valuedelivered) || competitive * 2;

const valueBased = value * captureRate;
const sweetSpot = Math.max(floor, Math.min(competitive, valueBased));
const premium = value * (captureRate + 0.1);

console.log("\n=== Pricing Strategy Calculator ===\n");
console.log(`  Cost Floor:        $${floor.toFixed(2)} (30% margin)`);
console.log(`  Competitive:       $${competitive.toFixed(2)}`);
console.log(`  Value Delivered:   $${value.toFixed(2)}`);
console.log(`  Capture Rate:      ${(captureRate * 100).toFixed(0)}% (configurable, target 10-30%)`);
console.log(`\n  RECOMMENDATIONS:`);
console.log(`  Budget (floor):    $${floor.toFixed(2)}`);
console.log(`  Sweet Spot:        $${sweetSpot.toFixed(2)}`);
console.log(`  Premium:            $${premium.toFixed(2)}`);
console.log(`\n  Strategy: ${value > competitive * 2 ? "Value-based pricing — emphasize ROI." : "Competitive pricing — highlight differentiation."}\n`);