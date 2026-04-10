import { TestBed, ComponentFixture } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { CommonModule } from '@angular/common';
import { of } from 'rxjs';
import { DashboardComponent } from './dashboard.component';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let component: DashboardComponent;
  let mockOrderService: { getOrders: jasmine.Spy; getOrderStats: jasmine.Spy };
  let mockBusinessService: { getSelectedBusinessId: jasmine.Spy };

  const mockStats = {
    total: 20, in_transit: 5, delivered: 10,
    delayed: 2, exception: 1, out_for_delivery: 2, picked_up: 0,
  };

  const mockOrders = [
    {
      id: 'ord-001', business_id: 'biz-001', tracking_number: '7489 2301 4456',
      origin: 'Memphis, TN', destination: 'New York, NY', status: 'Delivered' as const,
      weight_lbs: 12.5, service_type: 'Overnight' as const,
      estimated_delivery: '2026-04-05T17:00:00Z', actual_delivery: '2026-04-05T14:32:00Z',
      updated_at: '2026-04-05T14:32:00Z',
    },
    {
      id: 'ord-002', business_id: 'biz-001', tracking_number: '7489 2301 4457',
      origin: 'Memphis, TN', destination: 'Los Angeles, CA', status: 'In Transit' as const,
      weight_lbs: 3.2, service_type: 'Express' as const,
      estimated_delivery: '2026-04-08T17:00:00Z', actual_delivery: null,
      updated_at: '2026-04-07T09:15:00Z',
    },
  ];

  beforeEach(async () => {
    mockOrderService = {
      getOrders: jasmine.createSpy('getOrders'),
      getOrderStats: jasmine.createSpy('getOrderStats'),
    };
    mockBusinessService = {
      getSelectedBusinessId: jasmine.createSpy('getSelectedBusinessId'),
    };

    mockBusinessService.getSelectedBusinessId.and.returnValue(of(''));
    mockOrderService.getOrderStats.and.returnValue(of(mockStats));
    mockOrderService.getOrders.and.returnValue(of({ orders: mockOrders, total: 2, page: 1, limit: 10 }));

    await TestBed.configureTestingModule({
      imports: [RouterTestingModule, CommonModule],
      declarations: [DashboardComponent],
      providers: [
        { provide: OrderService, useValue: mockOrderService },
        { provide: BusinessService, useValue: mockBusinessService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load stats and orders on init', () => {
    expect(component.stats).toEqual(mockStats);
    expect(component.recentOrders.length).toBe(2);
    expect(component.loading).toBe(false);
  });

  it('should call getOrderStats with no businessId when none selected', () => {
    expect(mockOrderService.getOrderStats).toHaveBeenCalledWith(undefined);
  });

  it('should call getOrders with limit 10', () => {
    expect(mockOrderService.getOrders).toHaveBeenCalledWith(
      jasmine.objectContaining({ limit: 10 })
    );
  });

  it('should call getOrderStats with businessId when business selected', async () => {
    mockBusinessService.getSelectedBusinessId.and.returnValue(of('biz-001'));
    mockOrderService.getOrderStats.and.returnValue(of(mockStats));
    mockOrderService.getOrders.and.returnValue(of({ orders: [], total: 0, page: 1, limit: 10 }));

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();

    expect(mockOrderService.getOrderStats).toHaveBeenCalledWith('biz-001');
  });

  it('should return correct statusClass for "In Transit"', () => {
    expect(component.statusClass('In Transit')).toBe('badge badge-in-transit');
  });

  it('should return correct statusClass for "Out for Delivery"', () => {
    expect(component.statusClass('Out for Delivery')).toBe('badge badge-out-for-delivery');
  });

  it('should return "\u2014" from formatDate when null', () => {
    expect(component.formatDate(null)).toBe('\u2014');
  });

  it('should return formatted date string from formatDate', () => {
    const result = component.formatDate('2026-04-05T14:32:00Z');
    expect(result).toContain('2026');
    expect(result).toContain('Apr');
  });

  it('should render summary stat cards after loading', () => {
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('20');
  });
});
