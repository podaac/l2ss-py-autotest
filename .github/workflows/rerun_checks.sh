#!/bin/sh

git fetch --all

# Fetch open PRs and enable auto-merge on each one
pr_numbers=$(gh pr list --state open --json number | jq -r '.[].number')

for pr_number in $pr_numbers; do
    echo "Auto-merging PR number: $pr_number"
    gh pr merge --merge --auto $pr_number
done

gh pr list --state open --label $1 --limit 500 >branches.list
#git branch -r >branches.list

#cat branches.list
cat branches.list|grep diff\/ |sed 's|^.*diff/|diff/|g' |sed 's|\t.*||g' >branches2.list
#cat branches.list|grep \/diff\/ |sed 's|^.*(diff/.*?)\s/.*$|$1|g' >branches2.list
cat branches2.list                

#git config --global user.email ${{ github.actor }}@users.noreply.github.com
#git config --global user.name "${{ github.actor }}"

while read branch; do
  echo "Branch: $branch"
  git checkout $branch
  git pull origin $branch
  git merge main
  echo "git commit --allow-empty -m 'Triggering Autotest Workflow Re-Run'"
  git commit --allow-empty -m 'Triggering Autotest Workflow Re-Run'
  echo "git push origin $branch"
  git push origin $branch
done <branches2.list  

rm branches*.list
