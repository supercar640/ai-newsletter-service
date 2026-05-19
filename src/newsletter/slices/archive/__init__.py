"""Archive slice — push sent newsletter issues to external destinations.

Notion is the only target for now. The slice is structured so a Slack
archive or Notion-vs-Confluence swap is a new client + a new service
function, not a rewrite of the wiring.
"""
