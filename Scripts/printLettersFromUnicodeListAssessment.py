import sys
import urllib.request
from html.parser import HTMLParser


class TableParser(HTMLParser):
    """
    Extracts the first <table> in the document as a list of rows,
    where each row is a list of cell texts.
    """

    def __init__(self):
        super().__init__()
        self.inTable = False
        self.tableFound = False

        self.inTr = False
        self.inTd = False

        self.currentRow = []
        self.currentCell = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "table" and not self.tableFound:
            self.inTable = True
            return
        if not self.inTable:
            return

        if tag == "tr":
            self.inTr = True
            self.currentRow = []
        elif tag == "td" and self.inTr:
            self.inTd = True
            self.currentCell = []

    def handle_endtag(self, tag):
        if tag == "table" and self.inTable:
            # end of first table
            self.inTable = False
            self.tableFound = True
            return

        if not self.inTable:
            return

        if tag == "td" and self.inTd:
            # finish one cell
            text = "".join(self.currentCell).strip()
            self.currentRow.append(text)
            self.inTd = False
        elif tag == "tr" and self.inTr:
            # finish one row
            if self.currentRow:
                self.rows.append(self.currentRow)
            self.inTr = False

    def handle_data(self, data):
        if self.inTable and self.inTr and self.inTd:
            self.currentCell.append(data)


# Main orchestrator: fetch HTML, parse positions, build grid, and print it
def printGridFromDoc(url: str):
    html = fetchHtml(url)
    try:
        positions, maxX, maxY = parsePositionsFromHtml(html)
    except Exception as e:
        # Dump raw HTML for debugging
        print("=== BEGIN RAW HTML (for debugging) ===", file=sys.stderr)
        print(html, file=sys.stderr)
        print("===  END RAW HTML  ===", file=sys.stderr)
        raise

    grid = buildGrid(positions, maxX, maxY)
    printGrid(grid)


# Fetches raw HTML from the provided URL using urllib
def fetchHtml(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} fetching {url}")
        return resp.read().decode("utf-8")


# Parses the HTML table into a mapping of (x,y) to character
# Returns positions dict and maximum X and Y values
def parsePositionsFromHtml(html: str):
    parser = TableParser()
    parser.feed(html)

    if not parser.rows:
        raise ValueError("No table rows found")

    positions = {}
    maxX = maxY = 0

    for row in parser.rows:
        # Expect exactly 3 cells per data row
        if len(row) != 3:
            continue

        xTxt, char, yTxt = row
        if not (xTxt.isdigit() and yTxt.isdigit()):
            continue

        x, y = int(xTxt), int(yTxt)
        positions[(x, y)] = char
        maxX = max(maxX, x)
        maxY = max(maxY, y)

    if not positions:
        raise ValueError("No valid (x,character,y) rows parsed")

    return positions, maxX, maxY


# Builds a 2D grid (list of lists) filled with spaces, then places characters
# at their (x,y) coordinates
def buildGrid(positions, maxX: int, maxY: int):
    grid = [[" " for _ in range(maxX + 1)] for _ in range(maxY + 1)]
    for (x, y), ch in positions.items():
        grid[y][x] = ch
    return grid


# Prints the grid to stdout, flipping it vertically so y=0 prints first
def printGrid(grid):
    for row in reversed(grid):
        print("".join(row))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            f"Usage: python {sys.argv[0]} <published-google-doc-url>", file=sys.stderr
        )
        sys.exit(1)

    try:
        printGridFromDoc(sys.argv[1])
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
