export interface Product {
  sku: string;
  name: string;
  onHand: number;
  bin: string;
}

export const PRODUCTS: Product[] = [
  { sku: 'MUG-001', name: 'Enamel mug', onHand: 140, bin: 'A-01' },
  { sku: 'TEE-014', name: 'Organic tee (M)', onHand: 12, bin: 'B-07' },
  { sku: 'BAG-210', name: 'Canvas tote', onHand: 0, bin: 'B-11' },
  { sku: 'PEN-005', name: 'Brass pen', onHand: 61, bin: 'C-02' },
];

export const KNOWN_TAGS = ['fragile', 'cold-chain', 'oversize', 'gift-wrap', 'hazmat'];
