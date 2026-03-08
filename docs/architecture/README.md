# Architectuurdiagrammen — Baanschema

Deze map bevat 4 diagrammen (Mermaid bronbestanden):

1. `01-system-context.mmd` — systeemcontext (actoren + externe interacties)
2. `02-container-diagram.mmd` — containeroverzicht (UI/API/planner/data)
3. `03-deployment-diagram.mmd` — deployment/hosting overzicht
4. `04-ortools-solver-flow.mmd` — component/flow van OR-Tools solver pipeline

## Renderen naar SVG/PNG

Vanuit project-root:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/architecture/01-system-context.mmd -o docs/architecture/01-system-context.svg
npx -y @mermaid-js/mermaid-cli -i docs/architecture/02-container-diagram.mmd -o docs/architecture/02-container-diagram.svg
npx -y @mermaid-js/mermaid-cli -i docs/architecture/03-deployment-diagram.mmd -o docs/architecture/03-deployment-diagram.svg
npx -y @mermaid-js/mermaid-cli -i docs/architecture/04-ortools-solver-flow.mmd -o docs/architecture/04-ortools-solver-flow.svg
```

Optioneel PNG:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/architecture/01-system-context.mmd -o docs/architecture/01-system-context.png
```
