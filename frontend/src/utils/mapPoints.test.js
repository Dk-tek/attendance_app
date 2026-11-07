import test from 'node:test';
import assert from 'node:assert/strict';
import { validMapPoint } from './mapPoints.js';

test('missing, malformed and failed GPS events are not mapped to zero', () => {
  for (const point of [
    { latitude: null, longitude: null },
    { latitude: '', longitude: '' },
    { latitude: 999, longitude: 100 },
    { latitude: NaN, longitude: 12 },
    { latitude: 12, longitude: 77, tracking_status: 'failed' },
  ]) assert.equal(validMapPoint(point), false);
});
test('real zero coordinates and valid GPS coordinates are preserved', () => {
  assert.equal(validMapPoint({ latitude: 0, longitude: 0 }), true);
  assert.equal(validMapPoint({ latitude: 12.9, longitude: 77.6, tracking_status: 'ok' }), true);
});
