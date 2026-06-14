'use client';

import { useEffect, useState } from 'react';

export function CompanyMap() {
  const [MapComponent, setMapComponent] = useState<React.ComponentType<any> | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setMounted(true);
      // Dynamically import ALL Leaflet code only on client side
      Promise.all([
        import('leaflet'),
        import('react-leaflet'),
      ]).then(([LModule, ReactLeafletModule]) => {
        const L = LModule.default;
        const { MapContainer, TileLayer, Marker, Popup } = ReactLeafletModule;
        
        const customIcon = L.divIcon({
          html: `<i class="ki-solid ki-geolocation text-3xl text-green-500"></i>`,
          className: 'leaflet-marker',
          bgPos: [10, 10],
          iconAnchor: [20, 37],
          popupAnchor: [0, -37],
        });

        // Create a wrapper component that uses the dynamically imported components
        const DynamicMap = () => (
          <MapContainer
            center={[40.725, -73.985]}
            zoom={30}
            className="rounded-xl w-full md:w-80 min-h-52"
          >
            <TileLayer
              attribution='&copy; <a href="https://osm.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <Marker position={[40.724716, -73.984789]} icon={customIcon}>
              <Popup>430 E 6th St, New York, 10009.</Popup>
            </Marker>
          </MapContainer>
        );

        setMapComponent(() => DynamicMap);
      });
    }
  }, []);

  if (!mounted || !MapComponent) {
    return <div className="rounded-xl w-full md:w-80 min-h-52 bg-muted animate-pulse" />;
  }

  return <MapComponent />;
}
