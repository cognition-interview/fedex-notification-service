import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map, shareReplay, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { Order, OrderStats, OrderStatus, PaginatedOrders, ServiceType } from '../models/order.model';

export interface OrderFilters {
  businessId?: string;
  status?: OrderStatus;
  serviceType?: ServiceType;
  search?: string;
  page?: number;
  limit?: number;
}

type RawOrderStatsResponse = OrderStats | { by_status: Partial<OrderStats> };

@Injectable({ providedIn: 'root' })
export class OrderService {
  private ordersCache = new Map<string, Observable<PaginatedOrders>>();
  private orderByIdCache = new Map<string, Observable<Order | undefined>>();
  private orderStatsCache = new Map<string, Observable<OrderStats>>();

  constructor(private http: HttpClient) {}

  getOrders(filters?: OrderFilters): Observable<PaginatedOrders> {
    const key = JSON.stringify(filters ?? {});
    const cached = this.ordersCache.get(key);
    if (cached) return cached;

    let params = new HttpParams();
    if (filters?.businessId) params = params.set('businessId', filters.businessId);
    if (filters?.status) params = params.set('status', filters.status);
    if (filters?.serviceType) params = params.set('serviceType', filters.serviceType);
    if (filters?.search) params = params.set('search', filters.search);
    if (filters?.page) params = params.set('page', filters.page.toString());
    if (filters?.limit) params = params.set('limit', filters.limit.toString());

    const request$ = this.http
      .get<PaginatedOrders>(`${environment.apiUrl}/api/orders`, { params })
      .pipe(
        catchError(() => of({
          orders: [],
          total: 0,
          page: filters?.page ?? 1,
          limit: filters?.limit ?? 10,
        })),
        shareReplay(1),
      );

    this.ordersCache.set(key, request$);
    return request$;
  }

  getOrderById(id: string): Observable<Order | undefined> {
    const cached = this.orderByIdCache.get(id);
    if (cached) return cached;

    const request$ = this.http
      .get<Order & { events?: Order['shipment_events'] }>(`${environment.apiUrl}/api/orders/${id}`)
      .pipe(
        map(order => ({
          ...order,
          shipment_events: order.shipment_events ?? order.events ?? [],
        })),
        catchError(() => of(undefined)),
        shareReplay(1),
      );

    this.orderByIdCache.set(id, request$);
    return request$;
  }

  getOrderStats(businessId?: string): Observable<OrderStats> {
    const key = businessId ?? '__all__';
    const cached = this.orderStatsCache.get(key);
    if (cached) return cached;

    let params = new HttpParams();
    if (businessId) params = params.set('businessId', businessId);

    const request$ = this.http
      .get<RawOrderStatsResponse>(`${environment.apiUrl}/api/orders/stats`, { params })
      .pipe(
        map((raw: RawOrderStatsResponse) => {
          const base = raw && typeof raw === 'object' && 'by_status' in raw
            ? raw.by_status
            : raw;
          return this.normalizeOrderStats(base);
        }),
        catchError(() => of(this.emptyOrderStats())),
        shareReplay(1),
      );

    this.orderStatsCache.set(key, request$);
    return request$;
  }

  updateOrderStatus(id: string, payload: { status: OrderStatus; location?: string; description?: string }): Observable<Order> {
    return this.http
      .patch<Order & { events?: Order['shipment_events'] }>(`${environment.apiUrl}/api/orders/${id}/status`, payload)
      .pipe(
        map(order => ({
          ...order,
          shipment_events: order.shipment_events ?? order.events ?? [],
        })),
        tap(() => this.invalidateCache()),
      );
  }

  private invalidateCache(): void {
    this.ordersCache.clear();
    this.orderByIdCache.clear();
    this.orderStatsCache.clear();
  }

  private normalizeOrderStats(raw?: Partial<OrderStats>): OrderStats {
    return {
      total: this.toInt(raw?.total),
      in_transit: this.toInt(raw?.in_transit),
      delivered: this.toInt(raw?.delivered),
      delayed: this.toInt(raw?.delayed),
      exception: this.toInt(raw?.exception),
      out_for_delivery: this.toInt(raw?.out_for_delivery),
      picked_up: this.toInt(raw?.picked_up),
    };
  }

  private emptyOrderStats(): OrderStats {
    return {
      total: 0,
      in_transit: 0,
      delivered: 0,
      delayed: 0,
      exception: 0,
      out_for_delivery: 0,
      picked_up: 0,
    };
  }

  private toInt(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
}
