import { useEffect, useId, useRef } from "react";
import L from "leaflet";
import { validMapPoint } from "../utils/mapPoints.js";

export function MapView({ points, numbered = false, activePointId = null, onPointSelect }) {
  const mapRef = useRef(null);
  const markersRef = useRef(new Map());
  const selectRef = useRef(onPointSelect);
  selectRef.current = onPointSelect;
  const rawId = useId();
  const mapId = `attendanceMap-${rawId.replace(/:/g, "")}`;

  useEffect(() => {
    const map = L.map(mapId);
    mapRef.current = map;
    markersRef.current = new Map();
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(document.getElementById(mapId));
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);

    const valid = (points || []).filter(validMapPoint);
    const colors = {
      check_in: "#178f72",
      check_out: "#d1495b",
      location_track: "#2f6fed",
      attendance: "#b7791f"
    };

    if (!valid.length) {
      map.setView([20.5937, 78.9629], 5);
    } else {
      const sessions = new Map();
      for (const point of valid) {
        if (!point.session_id) continue;
        const key = `${point.employee_id}:${point.session_id}`;
        if (!sessions.has(key)) sessions.set(key, []);
        sessions.get(key).push(point);
      }
      for (const route of sessions.values()) {
        route.sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
        if (route.length > 1) L.polyline(route.map((point) => [point.latitude, point.longitude]), {
          color: "#2f6fed", weight: 2, opacity: 0.6, dashArray: "5, 5"
        }).addTo(map);
      }
      const markers = valid.map((point) => {
        const color = colors[point.type] || colors.attendance;
        const marker = numbered ? L.marker([point.latitude, point.longitude], {
          icon: L.divIcon({ className: "numberedMapIcon", html: `<span style="background:${color}">${point.pointNumber}</span>`, iconSize: [32, 32], iconAnchor: [16, 16] }),
          title: `Point ${point.pointNumber}: ${point.type}`,
          alt: `Point ${point.pointNumber}`,
          zIndexOffset: point.pointNumber || 0
        }).addTo(map) : L.circleMarker([Number(point.latitude), Number(point.longitude)], {
          radius: 7,
          color,
          fillColor: color,
          fillOpacity: 0.85,
          weight: 2
        }).addTo(map);
        const popup = document.createElement("div");
        for (const value of [point.employee_name || point.employee_id, point.type, point.display_timestamp || point.timestamp]) {
          const line = document.createElement("div");
          line.textContent = String(value ?? "");
          popup.appendChild(line);
        }
        marker.bindPopup(popup);
        if (point.id) markersRef.current.set(point.id, marker);
        marker.on("click", () => selectRef.current?.(point.id));
        return marker;
      });
      map.fitBounds(L.featureGroup(markers).getBounds().pad(0.16), { maxZoom: 16 });
    }

    return () => { observer.disconnect(); map.remove(); mapRef.current = null; markersRef.current.clear(); };
  }, [mapId, points, numbered]);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      marker.getElement()?.classList.toggle("activeMapPoint", id === activePointId);
      if (numbered) marker.setZIndexOffset(id === activePointId ? 10000 : 0);
    }
    const marker = markersRef.current.get(activePointId);
    if (marker) {
      mapRef.current.setView(marker.getLatLng(), Math.max(mapRef.current.getZoom(), 16));
      marker.openPopup();
    } else mapRef.current?.closePopup();
  }, [activePointId, points, numbered]);

  return <section className="mapPanel"><div className="attendanceMap" id={mapId} aria-label="Recorded employee locations" />{!(points || []).some(validMapPoint) ? <p>No recorded GPS locations available for this selection.</p> : null}<p>{numbered ? "Numbers match the timeline. Green: check-in. Blue: GPS. Red: check-out. " : ""}Dashed lines connect recorded points within one attendance session; they are not a measured travel path.</p></section>
}
