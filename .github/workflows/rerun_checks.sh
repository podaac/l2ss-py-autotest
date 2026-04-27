#!/bin/sh

echo "Starting script. Label argument provided: '$1'"

echo "Fetching all remote branches..."
git fetch --all

# Fetch open PRs and enable auto-merge on each one
echo "Fetching open PR numbers..."
pr_numbers=$(gh pr list --state open --json number --limit 500 | jq -r '.[].number')

echo "PR numbers found:"
echo "$pr_numbers"
echo "--------------------------------"

for pr_number in $pr_numbers; do
    # Skip if empty (just in case)
    [ -z "$pr_number" ] && continue
    echo "Auto-merging PR number: $pr_number"
    gh pr merge --merge --auto "$pr_number"
done

# Fetch PRs with the specified label and extract the branch names reliably
echo "Fetching branches for open PRs with label '$1'..."
gh pr list --state open --limit 500 --json headRefName | jq -r '.[].headRefName' | grep '^diff/' > branches2.list

echo "The contents of branches2.list are:"
cat branches2.list
echo "--------------------------------"

# Process each branch
while read -r branch; do
  # Failsafe: Skip if the line is empty
  [ -z "$branch" ] && continue

  echo "================================"
  echo "Currently processing branch: '$branch'"
  
  git checkout "$branch"
  git pull origin "$branch"
  
  echo "Merging main into '$branch'..."
  # Note: If this merge has conflicts, the script will pause or fail here.
  git merge origin/main 
  
  echo "Committing empty trigger commit..."
  git commit --allow-empty -m 'Triggering Autotest Workflow Re-Run'
  
  echo "Pushing to origin '$branch'..."
  # I have uncommented the push so it actually executes, 
  # but you can add a '#' in front of it if you are just doing a dry run.
  git push origin "$branch"
  
done < branches2.list  

# Clean up
echo "Cleaning up temporary files..."
rm -f branches2.list

echo "Script finished successfully!"