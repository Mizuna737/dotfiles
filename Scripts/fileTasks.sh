#!/usr/bin/env bash
set -euo pipefail

VAULT="/home/max/Documents/The Vault"
DAILY_DIR="$VAULT/Daily Notes"
PROJECTS_DIR="$VAULT/Projects"
PEOPLE_DIR="$VAULT/People"

parse_date() {
  local input="${1,,}"
  case "$input" in
  ponder) echo "ponder" ;;
  today) date +%Y-%m-%d ;;
  tomorrow) date -d "+1 day" +%Y-%m-%d ;;
  "next week") date -d "+7 days" +%Y-%m-%d ;;
  monday) date -d "next monday" +%Y-%m-%d ;;
  tuesday) date -d "next tuesday" +%Y-%m-%d ;;
  wednesday) date -d "next wednesday" +%Y-%m-%d ;;
  thursday) date -d "next thursday" +%Y-%m-%d ;;
  friday) date -d "next friday" +%Y-%m-%d ;;
  saturday) date -d "next saturday" +%Y-%m-%d ;;
  sunday) date -d "next sunday" +%Y-%m-%d ;;
  *) date -d "$input" +%Y-%m-%d 2>/dev/null || echo "" ;;
  esac
}

while true; do
  # Collect all incomplete tasks from daily notes + meetings
  # Also collect tasks from projects/people that are missing a domain tag
  declare -a TASK_LINES
  declare -a TASK_FILES
  declare -a TASK_INDICES
  declare -a TASK_FILED  # "true" = already in projects/people (update in-place)

  while IFS= read -r -d '' file; do
    mapfile -t lines <"$file"
    for i in "${!lines[@]}"; do
      if [[ "${lines[$i]}" =~ ^-\ \[\ \] ]]; then
        TASK_LINES+=("${lines[$i]}")
        TASK_FILES+=("$file")
        TASK_INDICES+=("$i")
        TASK_FILED+=("false")
      fi
    done
  done < <(find "$DAILY_DIR" "$VAULT/Meetings" -name "*.md" -print0)

  # Also collect undomain'd tasks from projects and people
  while IFS= read -r -d '' file; do
    mapfile -t lines <"$file"
    for i in "${!lines[@]}"; do
      if [[ "${lines[$i]}" =~ ^-\ \[\ \] ]] && \
         [[ ! "${lines[$i]}" =~ (#work|#household|#personal) ]]; then
        TASK_LINES+=("${lines[$i]}")
        TASK_FILES+=("$file")
        TASK_INDICES+=("$i")
        TASK_FILED+=("true")
      fi
    done
  done < <(find "$PROJECTS_DIR" "$PEOPLE_DIR" -name "*.md" -print0)

  if [ ${#TASK_LINES[@]} -eq 0 ]; then
    notify-send "File Task" "All tasks filed!"
    break
  fi

  # Build rofi task menu (annotate filed tasks with their source file)
  declare -a TASK_LABELS
  TASK_MENU="── Done ──"
  for i in "${!TASK_LINES[@]}"; do
    if [ "${TASK_FILED[$i]}" = "true" ]; then
      lbl="[$(basename "${TASK_FILES[$i]%.md}")] ${TASK_LINES[$i]}"
    else
      lbl="${TASK_LINES[$i]}"
    fi
    TASK_LABELS+=("$lbl")
    TASK_MENU="$TASK_MENU\n$lbl"
  done

  PICKED_TASK=$(printf "%b" "$TASK_MENU" | rofi -dmenu -p "File Task" -l 10) || break
  [ "$PICKED_TASK" = "── Done ──" ] && break
  [ -z "$PICKED_TASK" ] && break

  # Find which task was picked
  TASK_IDX=-1
  for i in "${!TASK_LABELS[@]}"; do
    if [ "${TASK_LABELS[$i]}" = "$PICKED_TASK" ]; then
      TASK_IDX=$i
      break
    fi
  done
  [ "$TASK_IDX" -eq -1 ] && continue

  IS_FILED="${TASK_FILED[$TASK_IDX]}"
  SOURCE_FILE="${TASK_FILES[$TASK_IDX]}"
  SOURCE_LINE_IDX="${TASK_INDICES[$TASK_IDX]}"
  TASK_LINE="${TASK_LINES[$TASK_IDX]}"

  # Due date prompt if missing (daily note tasks only)
  DUE_STR=""
  if [ "$IS_FILED" = "false" ] && [[ ! "$TASK_LINE" =~ \[\[ ]]; then
    DUE_INPUT=$(rofi -dmenu -p "Due date (e.g. 'friday', 'ponder', blank to skip)" -l 0) || true
    if [ -n "$DUE_INPUT" ] && [ "$DUE_INPUT" != "skip" ]; then
      PARSED_DATE=$(parse_date "$DUE_INPUT")
      if [ "$PARSED_DATE" = "ponder" ]; then
        DUE_STR=" #ponder"
      elif [ -n "$PARSED_DATE" ]; then
        DUE_STR=" [[$PARSED_DATE]]"
      else
        notify-send "File Task" "Couldn't parse date — filing without due date."
      fi
    fi
  fi

  # Priority prompt if missing (daily note tasks only)
  PRIORITY_STR=""
  if [ "$IS_FILED" = "false" ] && [[ ! "$TASK_LINE" =~ [⏫🔼🔽⏬] ]]; then
    PRIORITY=$(printf "⏫ Highest\n🔼 High\n➡ Normal\n🔽 Low\n⏬ Lowest\nskip" | rofi -dmenu -p "Priority" -l 6) || true
    case "$PRIORITY" in
    "⏫ Highest") PRIORITY_STR=" ⏫" ;;
    "🔼 High") PRIORITY_STR=" 🔼" ;;
    "➡ Normal") PRIORITY_STR="" ;;
    "🔽 Low") PRIORITY_STR=" 🔽" ;;
    "⏬ Lowest") PRIORITY_STR=" ⏬" ;;
    *) PRIORITY_STR="" ;;
    esac
  fi

  # Domain prompt if missing
  DOMAIN_TAG=""
  if [[ ! "$TASK_LINE" =~ (#work|#household|#personal) ]]; then
    DOMAIN_INPUT=$(printf "#work\n#household\n#personal\nskip" | rofi -dmenu -p "Domain" -l 4) || true
    case "$DOMAIN_INPUT" in
    "#work") DOMAIN_TAG=" #work" ;;
    "#household") DOMAIN_TAG=" #household" ;;
    "#personal") DOMAIN_TAG=" #personal" ;;
    *) DOMAIN_TAG="" ;;
    esac
  fi

  # Description prompt if missing
  DESC_STR=""
  if [[ ! "$TASK_LINE" =~ desc:: ]]; then
    DESC_INPUT=$(rofi -dmenu -p "Description (optional, blank to skip)" -l 0) || true
    if [ -n "$DESC_INPUT" ]; then
      DESC_STR=" [desc:: $DESC_INPUT]"
    fi
  fi

  # Build final task line
  FINAL_LINE="${TASK_LINE%%[[:space:]]}${PRIORITY_STR}${DUE_STR}${DOMAIN_TAG}${DESC_STR}"

  if [ "$IS_FILED" = "true" ]; then
    # Task is already in a project/people file — update in-place
    SOURCE_FILE="$SOURCE_FILE" SOURCE_LINE_IDX="$SOURCE_LINE_IDX" FINAL_LINE="$FINAL_LINE" python3 - <<'EOF'
import os
source_file = os.environ["SOURCE_FILE"]
source_line_idx = int(os.environ["SOURCE_LINE_IDX"])
final_line = os.environ["FINAL_LINE"]
with open(source_file, "r") as f:
    lines = f.readlines()
lines[source_line_idx] = final_line + "\n"
with open(source_file, "w") as f:
    f.writelines(lines)
EOF
    notify-send "File Task" "Updated in $(basename "${SOURCE_FILE%.md}")"
  else
    # Build destination list and move task from daily note
    DEST_MENU="── Done ──\n📋 + New Project\n👤 + New Person"
    declare -a DEST_FILES
    declare -a DEST_LABELS

    while IFS= read -r -d '' f; do
      label="📋 $(basename "${f%.md}")"
      DEST_MENU="$DEST_MENU\n$label"
      DEST_FILES+=("$f")
      DEST_LABELS+=("$label")
    done < <(find "$PROJECTS_DIR" -name "*.md" -print0)

    while IFS= read -r -d '' f; do
      label="👤 $(basename "${f%.md}")"
      DEST_MENU="$DEST_MENU\n$label"
      DEST_FILES+=("$f")
      DEST_LABELS+=("$label")
    done < <(find "$PEOPLE_DIR" -name "*.md" -print0)

    PICKED_DEST=$(printf "%b" "$DEST_MENU" | rofi -dmenu -p "File to" -l 10) || continue
    [ -z "$PICKED_DEST" ] && continue
    [ "$PICKED_DEST" = "── Done ──" ] && break

    # Resolve destination file
    DEST_FILE=""
    if [ "$PICKED_DEST" = "📋 + New Project" ]; then
      NEW_NAME=$(rofi -dmenu -p "New project name:" -l 0) || continue
      [ -z "$NEW_NAME" ] && continue
      DEST_FILE="$PROJECTS_DIR/$NEW_NAME.md"
      printf -- "---\nstatus: active\ntags: [project]\n---\n\n## Tasks\n" >"$DEST_FILE"
      notify-send "File Task" "Created project: $NEW_NAME"
    elif [ "$PICKED_DEST" = "👤 + New Person" ]; then
      NEW_NAME=$(rofi -dmenu -p "New person's name:" -l 0) || continue
      [ -z "$NEW_NAME" ] && continue
      DEST_FILE="$PEOPLE_DIR/$NEW_NAME.md"
      printf -- "---\ntags: [person]\n---\n\n## Tasks\n" >"$DEST_FILE"
      notify-send "File Task" "Created person: $NEW_NAME"
    else
      for i in "${!DEST_LABELS[@]}"; do
        if [ "${DEST_LABELS[$i]}" = "$PICKED_DEST" ]; then
          DEST_FILE="${DEST_FILES[$i]}"
          break
        fi
      done
    fi

    [ -z "$DEST_FILE" ] && continue

    # Insert task into destination file's ## Tasks section first
    DEST_FILE="$DEST_FILE" FINAL_LINE="$FINAL_LINE" python3 - <<'EOF'
import os, sys
dest_file = os.environ["DEST_FILE"]
final_line = os.environ["FINAL_LINE"]
with open(dest_file, "r") as f:
    lines = f.readlines()

idx = next((i for i, l in enumerate(lines) if l.strip() == "## Tasks"), None)

if idx is not None:
    insert_at = idx + 1
    while insert_at < len(lines) and (
        lines[insert_at].strip() == "" or
        lines[insert_at].strip().startswith("<!--") or
        lines[insert_at].strip().startswith("<--")
    ):
        insert_at += 1
    lines.insert(insert_at, final_line + "\n")
else:
    lines.append("\n## Tasks\n" + final_line + "\n")

with open(dest_file, "w") as f:
    f.writelines(lines)

sys.exit(0)
EOF

    # Only remove from source if insertion succeeded
    if [ $? -eq 0 ]; then
      SOURCE_FILE="$SOURCE_FILE" SOURCE_LINE_IDX="$SOURCE_LINE_IDX" python3 - <<'EOF'
import os
source_file = os.environ["SOURCE_FILE"]
source_line_idx = int(os.environ["SOURCE_LINE_IDX"])
with open(source_file, "r") as f:
    lines = f.readlines()
del lines[source_line_idx]
with open(source_file, "w") as f:
    f.writelines(lines)
EOF
    else
      notify-send "File Task" "⚠️ Insertion failed — task not removed from source."
    fi
    notify-send "File Task" "Filed to $(basename "${DEST_FILE%.md}")"
  fi

  # Reset arrays for next iteration
  unset TASK_LINES TASK_FILES TASK_INDICES TASK_FILED TASK_LABELS DEST_FILES DEST_LABELS
  declare -a TASK_LINES TASK_FILES TASK_INDICES TASK_FILED TASK_LABELS DEST_FILES DEST_LABELS

done
