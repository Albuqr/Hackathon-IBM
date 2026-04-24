Crisis Monitor — Fix Countries + Counters + Push
Read all project files before starting. Implement everything below then git push.

Fix 1 — Country dropdown shows combined entries
The country dropdown shows entries like "Austria, Belarus, Czech Republic..."
as a single option because the database stores multiple countries in one field.
Fix:

In middleware/main.py and frontend/app.py, when building the country list,
split each country field by comma, strip whitespace, treat each as individual
Deduplicate and sort A-Z
When filtering by country, match events where country field contains that name


Fix 2 — Volunteer and ONG counters in popup
Add a crisis_associations table to the database:
id, crisis_id, user_id, role (volunteer or org), created_at
Add endpoint GET /events/{crisis_id}/associations in middleware/main.py
returning: { "volunteers": N, "orgs": N }
In the popup in base.html, after it opens fetch that endpoint and display:
"Voluntários mobilizados: N"
"ONGs associadas: N"
Show a loading indicator while fetching.
Do NOT add any enlist button — just show the read-only counters.
also, if the new agent is not on watsonx please run the stuff to upload it there
ultrathink

After implementing both fixes
Run: git add -A && git commit -m "Adicionei o esboço do front end, mapa funcionando com paises e filtros, muitos bug fixes e funcionalidades no mapinha, novo agente de predição de disastres e guerras entre outras coisas" && git push