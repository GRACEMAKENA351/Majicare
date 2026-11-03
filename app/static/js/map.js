(function () {
    var mapElement = document.getElementById("water-points-map");
    var dataElement = document.getElementById("water-points-data");

    if (!mapElement || !dataElement) {
        return;
    }

    var unavailableNotice = mapElement.parentElement.querySelector(".map-unavailable");
    if (!window.L) {
        if (unavailableNotice) {
            unavailableNotice.hidden = false;
        }
        return;
    }

    var waterPoints = JSON.parse(dataElement.textContent || "[]");
    var map = L.map(mapElement, { scrollWheelZoom: false }).setView([-0.5, 37.9], 6);
    var tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors"
    }).addTo(map);

    tiles.on("tileerror", function () {
        if (unavailableNotice) {
            unavailableNotice.hidden = false;
        }
    });

    var markers = [];
    waterPoints.forEach(function (point) {
        var latitude = Number(point.latitude);
        var longitude = Number(point.longitude);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
            latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
            return;
        }

        var color = "#4d83cc";
        if (point.status === "Operational") {
            color = "#2ba478";
        } else if (point.status === "Needs Inspection") {
            color = "#e89a35";
        } else if (point.status === "Out of Service") {
            color = "#dd5b69";
        }

        var marker = L.circleMarker([latitude, longitude], {
            radius: 8,
            color: "#ffffff",
            weight: 2,
            fillColor: color,
            fillOpacity: 0.95
        }).addTo(map);
        var popup = document.createElement("div");
        var name = document.createElement("strong");
        var details = document.createElement("p");
        name.textContent = point.name;
        details.textContent = point.community + " · " + point.status;
        details.style.margin = "4px 0 0";
        popup.append(name, details);
        marker.bindPopup(popup);
        markers.push(marker);
    });

    if (markers.length > 1) {
        map.fitBounds(L.featureGroup(markers).getBounds().pad(0.18));
    } else if (markers.length === 1) {
        map.setView(markers[0].getLatLng(), 12);
    }
})();