import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';
import { OrderDetailComponent } from './order-detail.component';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';

describe('OrderDetailComponent', () => {
  let fixture: ComponentFixture<OrderDetailComponent>;
  let component: OrderDetailComponent;
  let mockOrderService: jasmine.SpyObj<OrderService>;
  let mockBusinessService: jasmine.SpyObj<BusinessService>;

  const mockOrder = {
    id: 'ord-001', business_id: 'biz-001', tracking_number: '7489 2301 4456',
    origin: 'Memphis, TN', destination: 'New York, NY', status: 'Delivered' as const,
    weight_lbs: 12.5, service_type: 'Overnight' as const,
    estimated_delivery: '2026-04-05T17:00:00Z', actual_delivery: '2026-04-05T14:32:00Z',
    updated_at: '2026-04-05T14:32:00Z',
    shipment_events: [
      { id: 'evt-001', order_id: 'ord-001', event_type: 'Delivered', location: 'New York, NY',
        description: 'Package delivered', occurred_at: '2026-04-05T14:32:00Z' },
      { id: 'evt-002', order_id: 'ord-001', event_type: 'In Transit', location: 'Newark, NJ',
        description: 'Arrived at facility', occurred_at: '2026-04-05T03:20:00Z' },
      { id: 'evt-003', order_id: 'ord-001', event_type: 'Picked Up', location: 'Memphis, TN',
        description: 'Package picked up', occurred_at: '2026-04-04T15:00:00Z' },
    ],
  };

  const mockBusiness = {
    id: 'biz-001', name: 'Acme Electronics', account_number: 'FDX-10042881',
    address: '123 Industrial Blvd, Memphis, TN', contact_email: 'gb555@cornell.edu',
    phone: '901-555-0101',
  };

  function createComponent(orderId = 'ord-001', order: any = mockOrder) {
    return TestBed.configureTestingModule({
      imports: [OrderDetailComponent],
      providers: [
        provideRouter([]),
        { provide: OrderService, useValue: mockOrderService },
        { provide: BusinessService, useValue: mockBusinessService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { paramMap: convertToParamMap({ id: orderId }) },
          },
        },
      ],
    }).compileComponents().then(() => {
      mockOrderService.getOrderById.and.returnValue(of(order));
      mockBusinessService.getBusinessById.and.returnValue(of(mockBusiness));
      fixture = TestBed.createComponent(OrderDetailComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
      return fixture.whenStable();
    });
  }

  beforeEach(async () => {
    mockOrderService = jasmine.createSpyObj('OrderService', ['getOrderById']);
    mockBusinessService = jasmine.createSpyObj('BusinessService', ['getBusinessById']);
    await createComponent();
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load order on init', () => {
    expect(component.order).toEqual(mockOrder);
    expect(component.loading).toBeFalse();
    expect(component.notFound).toBeFalse();
  });

  it('should load business for the order', () => {
    expect(component.business).toEqual(mockBusiness);
    expect(mockBusinessService.getBusinessById).toHaveBeenCalledWith('biz-001');
  });

  it('should set notFound when order is undefined', async () => {
    mockOrderService.getOrderById.and.returnValue(of(undefined));
    fixture = TestBed.createComponent(OrderDetailComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    expect(component.notFound).toBeTrue();
    expect(component.loading).toBeFalse();
  });

  it('should return sortedEvents in descending occurred_at order', () => {
    const sorted = component.sortedEvents;
    expect(sorted.length).toBe(3);
    // Most recent first
    expect(sorted[0].event_type).toBe('Delivered');
    expect(sorted[2].event_type).toBe('Picked Up');
  });

  it('should return empty array for sortedEvents when no shipment_events', () => {
    component.order = { ...mockOrder, shipment_events: undefined };
    expect(component.sortedEvents).toEqual([]);
  });

  it('should render tracking number in the template', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('7489 2301 4456');
  });

  it('should render shipment timeline events', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('Memphis, TN');
  });

  it('should return correct statusClass', () => {
    expect(component.statusClass('Delivered')).toBe('badge badge-delivered');
    expect(component.statusClass('Out for Delivery')).toBe('badge badge-out-for-delivery');
  });

  it('should return "\u2014" from formatDate when null', () => {
    expect(component.formatDate(null)).toBe('\u2014');
  });

  it('should return formatted date from formatDate', () => {
    const result = component.formatDate('2026-04-05T14:32:00Z');
    expect(result).toContain('Apr');
  });

  it('should return "\u2014" from formatDateTime when null', () => {
    expect(component.formatDateTime(null)).toBe('\u2014');
  });
});
