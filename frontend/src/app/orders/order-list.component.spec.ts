import { TestBed, ComponentFixture } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';
import { OrderListComponent } from './order-list.component';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';

describe('OrderListComponent', () => {
  let fixture: ComponentFixture<OrderListComponent>;
  let component: OrderListComponent;
  let mockOrderService: { getOrders: jasmine.Spy };
  let mockBusinessService: { getSelectedBusinessId: jasmine.Spy };

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
    };
    mockBusinessService = {
      getSelectedBusinessId: jasmine.createSpy('getSelectedBusinessId'),
    };

    mockBusinessService.getSelectedBusinessId.and.returnValue(of(''));
    mockOrderService.getOrders.and.returnValue(of({ orders: mockOrders, total: 2, page: 1, limit: 10 }));

    await TestBed.configureTestingModule({
      imports: [RouterTestingModule, CommonModule, FormsModule],
      declarations: [OrderListComponent],
      providers: [
        { provide: OrderService, useValue: mockOrderService },
        { provide: BusinessService, useValue: mockBusinessService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParamMap: convertToParamMap({}) },
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(OrderListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load and render orders on init', () => {
    expect(component.orders.length).toBe(2);
    expect(component.total).toBe(2);
  });

  it('should render table rows for each order', () => {
    const rows = (fixture.nativeElement as HTMLElement).querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThanOrEqual(2);
  });

  it('should display tracking numbers in rows', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('7489 2301 4456');
  });

  it('should apply status filter and call loadOrders', () => {
    component.filterStatus = 'Delivered';
    component.applyFilters();
    expect(mockOrderService.getOrders).toHaveBeenCalledWith(
      jasmine.objectContaining({ status: 'Delivered' })
    );
    expect(component.page).toBe(1);
  });

  it('should reset to page 1 when filters applied', () => {
    component.page = 3;
    component.applyFilters();
    expect(component.page).toBe(1);
  });

  it('should decrement page on prevPage', () => {
    component.page = 3;
    component.total = 25;
    component.prevPage();
    expect(component.page).toBe(2);
  });

  it('should not go below page 1 on prevPage', () => {
    component.page = 1;
    component.prevPage();
    expect(component.page).toBe(1);
  });

  it('should increment page on nextPage', () => {
    component.page = 1;
    component.total = 25;
    component.nextPage();
    expect(component.page).toBe(2);
  });

  it('should not go past last page on nextPage', () => {
    component.page = 3;
    component.total = 25;
    component.nextPage();
    expect(component.page).toBe(3);
  });

  it('should compute totalPages correctly', () => {
    component.total = 25;
    expect(component.totalPages).toBe(3);
  });

  it('should compute pageStart correctly', () => {
    component.page = 2;
    expect(component.pageStart).toBe(11);
  });

  it('should compute pageEnd correctly', () => {
    component.page = 2;
    component.total = 25;
    expect(component.pageEnd).toBe(20);
  });

  it('should return correct statusClass', () => {
    expect(component.statusClass('In Transit')).toBe('badge badge-in-transit');
    expect(component.statusClass('Delivered')).toBe('badge badge-delivered');
    expect(component.statusClass('Exception')).toBe('badge badge-exception');
  });

  it('should return "\u2014" for null date', () => {
    expect(component.formatDate(null)).toBe('\u2014');
  });
});
