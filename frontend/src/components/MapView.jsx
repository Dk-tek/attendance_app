import { useEffect, useId } from "react";
import L from "leaflet";

export function MapView({ points }) {
  const rawId = useId();
  const mapId = `attendanceMap-${rawId.replace(/:/g, "")}`;

  useEffect(() => {
    const map = L.map(mapId);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);

    const valid = points.filter((point) => Number.isFinite(Number(point.latitude)) && Number.isFinite(Number(point.longitude)));
    const colors = {
      check_in: "#178f72",
      check_out: "#d1495b",
      location_track: "#2f6fed",
      attendance: "#b7791f"
    };

    if (!valid.length) {
      map.setView([20.5937, 78.9629], 5);
    } else {
      const markers = valid.map((point) => {
        const color = colors[point.type] || colors.attendance;
        const marker = L.circleMarker([Number(point.latitude), Number(point.longitude)], {
          radius: 7,
          color,
          fillColor: color,
          fillOpacity: 0.85,
          weight: 2
        }).addTo(map);
        marker.bindPopup(`${point.employee_name || point.employee_id}<br>${point.type}<br>${point.display_timestamp || point.timestamp}`);
        return marker;
      });
      map.fitBounds(L.featureGroup(markers).getBounds().pad(0.16));
    }

    return () => map.remove();
  }, [mapId, points]);

  return <section className="mapPanel"><div className="attendanceMap" id={mapId} /></section>;
}
