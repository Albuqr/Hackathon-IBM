# Crisis Monitor — Fix Volunteer Map Showing Only 20 Events

The volunteer map at /volunteer/map is only showing 20 crisis events
instead of all 150+. The admin map shows all events correctly.
Something broke during the last implementation session.

Read all files before doing anything. Investigate and fix.

## What to check

1. In frontend/app.py, find the route for /volunteer/map. Compare how it
   fetches events versus how /map (admin) fetches events. They should call
   the same API endpoint with the same parameters. If the volunteer route
   has a different limit, filter, or query parameter, remove it.

2. In middleware/main.py, check the GET /events endpoint. Make sure there
   is no role-based filtering that limits results for volunteers. All roles
   should receive all events.

3. Check if a LIMIT clause was accidentally added to the SQL query in /events
   during the last session. Remove any hardcoded LIMIT that is lower than 500.

4. The screenshot shows only conflict-type events (red dots, all in the
   Middle East). This suggests the crisis_type filter might be defaulting
   to "conflict" for volunteer users, or the seed_volunteers.py script
   created events that are interfering with the query.

5. Check the JavaScript in the volunteer map template. If it has a different
   initial filter applied on load compared to the admin map, reset it to
   show all events by default.

Fix whatever is causing the discrepancy. The rule is simple:

ALL crisis events must be visible on the map for ALL user roles —
admin, volunteer, and org — with no filters applied by default.
No role should ever see fewer events than another role.
No crisis type, severity, or region filter should be active on page load.
Every route that renders a map must pass the full unfiltered event list.

After fixing, log into all three roles and confirm each sees 150+ events.