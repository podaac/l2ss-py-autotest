#!/bin/sh

git fetch --all

# Fetch open PRs and enable auto-merge on each one
pr_numbers=$(gh pr list --state open --json number | jq -r '.[].number')

for pr_number in $pr_numbers; do
    echo "Auto-merging PR number: $pr_number"
    gh pr merge --merge --auto $pr_number
done

gh pr list --state open --label "$1" --json number,headRefName,headRepository | \
  jq -r '.[] | select(.headRepository.isFork==false) | "\(.number)\t\(.headRefName)"' >branches.list

cat branches.list

#git config --global user.email ${{ github.actor }}@users.noreply.github.com
#git config --global user.name "${{ github.actor }}"

while IFS=$'\t' read pr_number branch; do
  if [ -z "$branch" ]; then
    continue
  fi
  echo "PR: $pr_number Branch: $branch"
  git fetch origin "$branch"
  git checkout -B "$branch" "origin/$branch"
  git fetch origin main
  if ! git merge origin/main; then
    echo "Merge conflict on $branch; aborting merge and continuing with empty commit."
    git merge --abort || true
  fi
  echo "git commit --allow-empty -m 'Triggering Autotest Workflow Re-Run'"
  git commit --allow-empty -m 'Triggering Autotest Workflow Re-Run'
  echo "git push origin $branch"
  git push origin "$branch"
done <branches.list

rm -f branches.list
