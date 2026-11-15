import QtQuick
import QtQuick.Layouts
import QtQml.Models
import org.kde.plasma.plasmoid
import "Order.js" as Order

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Layout.minimumWidth: 0
    Layout.preferredWidth: 0
    Layout.maximumWidth: 0
    Layout.minimumHeight: 0
    property var grid: null
    property var originalModel: null
    property var orderedModel: null
    property string lastReport: ""
    fullRepresentation: Item { implicitWidth: 0; implicitHeight: 0 }

    Component { id: modelFactory; DelegateModel {} }

    function findTray(item, depth) {
        if (!item || depth > 18) return null;
        if (item.visibleLayout !== undefined && item.systemTrayState !== undefined)
            return item.visibleLayout;
        const kids = item.children || [];
        for (let i = 0; i < kids.length; ++i) {
            const found = findTray(kids[i], depth + 1);
            if (found) return found;
        }
        return null;
    }
    function updateOrder() {
        if (!grid) {
            let top = root;
            while (top.parent) top = top.parent;
            grid = findTray(top, 0);
            if (!grid) return;
            originalModel = grid.model;
            orderedModel = modelFactory.createObject(root, {
                "model": originalModel, "delegate": grid.delegate
            });
            grid.model = orderedModel;
        }
        if (!orderedModel) return;
        let ids = [];
        for (let i = 0; i < orderedModel.items.count; ++i)
            ids.push(String(orderedModel.items.get(i).model.itemId));
        const desired = Order.desiredOrder(ids);
        for (let i = 0; i < desired.length; ++i) {
            const from = ids.indexOf(desired[i]);
            if (from !== i) {
                orderedModel.items.move(from, i, 1);
                ids.splice(i, 0, ids.splice(from, 1)[0]);
            }
        }
        const report = ids.join(" → ");
        if (report !== lastReport) {
            console.warn("CALLAS_TRAY_ORDER: " + report);
            lastReport = report;
        }
    }
    Timer { interval: 1500; repeat: true; running: true; onTriggered: root.updateOrder() }
    Component.onDestruction: {
        if (grid && originalModel) grid.model = originalModel;
    }
}
