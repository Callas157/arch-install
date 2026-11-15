.pragma library
function desiredOrder(ids) {
    const batteries = ["Callas Baterias", "indicator-solaar"];
    if (ids.indexOf("org.kde.plasma.networkmanagement") < 0) return ids.slice();
    const result = ids.filter(id => batteries.indexOf(id) < 0);
    const before = result.indexOf("org.kde.plasma.networkmanagement");
    const present = batteries.filter(id => ids.indexOf(id) >= 0);
    result.splice(before, 0, ...present);
    return result;
}
