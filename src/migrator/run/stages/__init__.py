"""The run's nodes, by stage: prepare (Scan, Pre-check, Rules), verify (after Rules and
final), queue (plan, next file, recheck), file_loop (start file, agent, tools, file
end), review, commits and report. Each node reads the state, calls its stage's domain
function and returns the keys it changed."""
