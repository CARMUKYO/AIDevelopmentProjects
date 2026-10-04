// ExpenseStatus.qml — drop-in Quickshell bar widget for the expense tracker.
//
// Expects `expense status --json` on PATH with schema:
// {"text","tooltip","month_total","budget","percent","state","currency"}.
// state is one of "ok" | "warning" | "over".
//
// NOTE (honest uncertainty): Quickshell's QML API evolves quickly. This was
// written against the documented Quickshell.Io Process + StdioCollector
// pattern (Quickshell 0.x). If your version renamed StdioCollector/SplitParser
// props, check `quickshell --help` / the Io docs for your release. The JSON
// parsing and Timer logic below is plain QtQuick and should carry over.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

Item {
    id: root
    // Size to the label so it fits naturally in a bar RowLayout.
    implicitWidth: label.implicitWidth + 16
    implicitHeight: 28

    property string displayText: "--"
    property string tooltipText: "Loading…"
    property string expenseState: "ok"
    property color okColor: "#7dd87d"
    property color warningColor: "#e5c07b"
    property color overColor: "#e06c75"

    function stateColor(): color {
        if (expenseState === "warning")
            return warningColor;
        if (expenseState === "over")
            return overColor;
        return okColor;
    }

    function refresh() {
        // Restarting the process re-runs `expense status --json`.
        statusProc.running = false;
        statusProc.running = true;
    }

    function handleOutput(text: string) {
        // Never crash the bar on empty or invalid output.
        if (!text || !text.trim()) {
            return;
        }
        var data = null;
        try {
            data = JSON.parse(text);
        } catch (e) {
            return;
        }
        if (data === null || typeof data !== "object") {
            return;
        }
        if (typeof data.text === "string" && data.text.length > 0) {
            root.displayText = data.text;
        }
        if (typeof data.tooltip === "string") {
            root.tooltipText = data.tooltip;
        }
        if (data.state === "ok" || data.state === "warning" || data.state === "over") {
            root.expenseState = data.state;
        }
    }

    // Poll the CLI every 60 seconds.
    Timer {
        id: pollTimer
        interval: 60000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Process {
        id: statusProc
        command: ["expense", "status", "--json"]
        stdout: StdioCollector {
            onStreamFinished: root.handleOutput(this.text)
        }
        // Ignore stderr/exit code: degraded output still parses, and the
        // widget keeps its last good value on failure.
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.displayText
        color: root.stateColor()
        font.pixelSize: 13
    }

    // Click anywhere on the widget to refresh immediately.
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.refresh()
        // Native tooltip on hover showing the multi-line breakdown.
        ToolTip.visible: containsMouse
        ToolTip.delay: 400
        ToolTip.text: root.tooltipText
    }
}
