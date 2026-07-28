// Fixture: High Cyclomatic Complexity (JavaScript, role=utility, warn>=10).
function tangledJs(a, b) {
  let t = 0;
  if (a > 0) { t++; }
  if (b > 0) { t++; }
  if (a && b) { t++; }
  if (a || b) { t++; }
  for (let i = 0; i < a; i++) {
    if (i % 2) { t += i; }
  }
  while (t < 50) { t++; }
  switch (a) {
    case 1: t++; break;
    case 2: t++; break;
  }
  return t > 0 ? t : -t;       // TP high_complexity (cc ~13)
}

const simpleJs = (x) => x + 1;  // decoy: cc 1
