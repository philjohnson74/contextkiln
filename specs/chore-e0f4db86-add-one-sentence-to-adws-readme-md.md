# Chore: Add one sentence to adws/README.md

## Metadata
adw_id: `e0f4db86`
prompt: `Add one sentence to adws/README.md, directly under the script table, telling readers to run adw_health_check.py before starting a workflow.`

## Chore Description
Add a single sentence to the adws/README.md file directly under the script table, informing readers that they should run adw_health_check.py before starting any workflow.

## Relevant Files
Use these files to complete the chore:

- `adws/README.md` - The target file where we need to add the sentence
- `specs/chore-e0f4db86-add-one-sentence-to-adws-readme-md.md` - The plan file being created

## Step by Step Tasks
### 1. Add sentence to adws/README.md
- Locate the script table in adws/README.md (around line 5-12)
- Add a new sentence directly under the table that tells readers to run adw_health_check.py before starting a workflow
- The sentence should be: "Before starting any workflow, run `adw_health_check.py` to ensure all tools and dependencies are properly configured."

### 2. Validate the work
- Check that the sentence was added correctly
- Verify that the file still renders properly

## Validation Commands
Execute these commands to validate the chore is complete:

- `cat adws/README.md` - Display the file to verify the new sentence was added
- `./adws/adw_health_check.py` - Run the health check script to ensure it works

## Notes
The sentence should be placed directly under the script table in adws/README.md, as specified in the chore prompt.