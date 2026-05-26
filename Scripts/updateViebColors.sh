#!/bin/bash

# Generate ~/.config/Vieb/colors/pywal.css from pywal colors

WAL_ENV="$HOME/.cache/wal/colors.env"
VIEB_CSS="$HOME/.config/Vieb/colors/pywal.css"

if [[ ! -f "$WAL_ENV" ]]; then
	echo "❌ Missing wal color export file: $WAL_ENV"
	exit 1
fi

# shellcheck disable=SC1090
source "$WAL_ENV"

mkdir -p "$(dirname "$VIEB_CSS")"

cat >"$VIEB_CSS" <<EOF
/* Auto-generated from pywal by updateViebColors.sh */
:root {
    /* general */
    --bg: ${WAL_BACKGROUND};
    --fg: ${WAL_FOREGROUND};
    --tab-background: ${WAL_BACKGROUND};
    --tab-suspended: ${WAL_COLOR0};
    --visible-tab: ${WAL_COLOR8};
    --tab-split: ${WAL_COLOR4};
    --tab-audio: ${WAL_COLOR5};
    --tab-muted: ${WAL_COLOR5};
    --tab-muted-playing: ${WAL_COLOR3};
    --tab-crashed: ${WAL_COLOR1};
    --tab-unresponsive: ${WAL_COLOR1};
    --tab-scrollbar: ${WAL_COLOR8};
    --container-background: none;
    --mode-normal-fg: ${WAL_FOREGROUND};
    --mode-normal-bg: none;
    --mode-command-fg: ${WAL_COLOR1};
    --mode-command-bg: none;
    --mode-insert-fg: ${WAL_COLOR2};
    --mode-insert-bg: none;
    --mode-follow-fg: ${WAL_COLOR5};
    --mode-follow-bg: none;
    --mode-explore-fg: ${WAL_COLOR4};
    --mode-explore-bg: none;
    --mode-search-fg: ${WAL_COLOR3};
    --mode-search-bg: none;
    --mode-pointer-fg: ${WAL_COLOR8};
    --mode-pointer-bg: ${WAL_FOREGROUND};
    --mode-visual-fg: ${WAL_COLOR0};
    --mode-visual-bg: ${WAL_COLOR4};
    --url-default: ${WAL_FOREGROUND};
    --url-search: ${WAL_COLOR3};
    --url-searchwords: ${WAL_COLOR5};
    --url-url: ${WAL_COLOR4};
    --url-suggest: ${WAL_COLOR2};
    --url-file: ${WAL_COLOR6};
    --url-invalid: ${WAL_COLOR1};
    --follow-text: ${WAL_FOREGROUND};
    --follow-url-bg: ${WAL_COLOR9};
    --follow-url-border: ${WAL_COLOR9};
    --follow-url-hover: ${WAL_COLOR9}77;
    --follow-click-bg: ${WAL_COLOR10};
    --follow-click-border: ${WAL_COLOR10};
    --follow-click-hover: ${WAL_COLOR10}77;
    --follow-insert-bg: ${WAL_COLOR11};
    --follow-insert-border: ${WAL_COLOR11};
    --follow-insert-hover: ${WAL_COLOR11}77;
    --follow-onclick-bg: ${WAL_COLOR12};
    --follow-onclick-border: ${WAL_COLOR12};
    --follow-onclick-hover: ${WAL_COLOR12}77;
    --follow-media-bg: ${WAL_COLOR13};
    --follow-media-border: ${WAL_COLOR13};
    --follow-media-hover: ${WAL_COLOR13}77;
    --follow-image-bg: ${WAL_COLOR14};
    --follow-image-border: ${WAL_COLOR14};
    --follow-image-hover: ${WAL_COLOR14}77;
    --follow-other-bg: ${WAL_COLOR15};
    --follow-other-border: ${WAL_COLOR15};
    --follow-other-hover: ${WAL_COLOR15}77;
    --suggestions-border: ${WAL_COLOR8};
    --suggestions-bg: ${WAL_BACKGROUND};
    --suggestions-selected: ${WAL_COLOR8};
    --suggestions-searchwords: ${WAL_COLOR5};
    --suggestions-url: ${WAL_COLOR9};
    --suggestions-file: ${WAL_COLOR12};
    --notification-border: ${WAL_COLOR8};
    --notification-date: ${WAL_COLOR8};
    --notification-permission: ${WAL_COLOR8};
    --notification-dialog: ${WAL_COLOR8};
    --notification-error: ${WAL_COLOR1};
    --notification-warning: ${WAL_COLOR3};
    --notification-info: ${WAL_COLOR4};
    --notification-success: ${WAL_COLOR2};
    --url-hover-fg: ${WAL_FOREGROUND};
    --url-hover-bg: ${WAL_BACKGROUND};
    --screenshot-highlight: ${WAL_COLOR4};
    --screenshot-highlight-background: ${WAL_COLOR4}77;
    /* special pages */
    --link-color: ${WAL_COLOR4};
    --link-underline: ${WAL_COLOR4};
    --scrollbar-bg: ${WAL_BACKGROUND};
    --scrollbar-thumb: ${WAL_COLOR8};
    --button-disabled: ${WAL_COLOR8};
    --code-fg: ${WAL_FOREGROUND};
    --code-bg: ${WAL_BACKGROUND};
    --code-command: ${WAL_COLOR1};
    --placeholder-text: ${WAL_COLOR8};
    --special-page-element-bg: ${WAL_BACKGROUND};
    --special-page-element-border: ${WAL_COLOR8};
    --input-unfocused: ${WAL_COLOR8};
    --input-focused: ${WAL_FOREGROUND};
    --download-progress-fg: ${WAL_FOREGROUND};
    --download-progress-bg: ${WAL_COLOR8};
    --helppage-h1: ${WAL_COLOR1};
    --helppage-h2: ${WAL_COLOR3};
    --helppage-h3: ${WAL_COLOR6};
    --helppage-countable: ${WAL_COLOR3};
    --helppage-range-compat: ${WAL_COLOR3};
    --helppage-nativetheme-fg-light: ${WAL_COLOR15};
    --helppage-nativetheme-bg-light: ${WAL_FOREGROUND};
    --helppage-nativetheme-fg-dark: ${WAL_COLOR8};
    --helppage-nativetheme-bg-dark: ${WAL_COLOR0};
    --history-current-page-highlight: ${WAL_COLOR1};
    /* sourceviewer */
    --syntax-fg: ${WAL_FOREGROUND};
    --syntax-bg: ${WAL_BACKGROUND};
    --syntax-keyword: ${WAL_COLOR1};
    --syntax-entity: ${WAL_COLOR4};
    --syntax-constant: ${WAL_COLOR9};
    --syntax-string: ${WAL_COLOR2};
    --syntax-variable: ${WAL_COLOR6};
    --syntax-comment: ${WAL_COLOR8};
    --syntax-entity-tag: ${WAL_COLOR3};
    --syntax-markup-heading: ${WAL_COLOR4};
    --syntax-markup-list: ${WAL_COLOR6};
    --syntax-markup-emphasis: ${WAL_COLOR8};
    --syntax-markup-addition-fg: ${WAL_COLOR2};
    --syntax-markup-addition-bg: ${WAL_COLOR2}22;
    --syntax-markup-deletion-fg: ${WAL_COLOR1};
    --syntax-markup-deletion-bg: ${WAL_COLOR1}22;
    /* failedload */
    --failedload-main-bg: ${WAL_BACKGROUND};
    /* filebrowser */
    --filebrowser-main-bg: ${WAL_BACKGROUND};
    --filebrowser-dir: ${WAL_COLOR12};
    --filebrowser-file: ${WAL_COLOR9};
    --filebrowser-breadcrumb: ${WAL_COLOR9};
    --filebrowser-error: ${WAL_COLOR1};
}
EOF

echo "✅ Vieb pywal theme generated at $VIEB_CSS"
