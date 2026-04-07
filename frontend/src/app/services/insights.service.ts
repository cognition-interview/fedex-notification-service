import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map, shareReplay } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { DeliveryInsights } from '../models/insight.model';

@Injectable({ providedIn: 'root' })
export class InsightsService {
  private insightsCache$?: Observable<DeliveryInsights>;

  constructor(private http: HttpClient) {}

  getDeliveryInsights(): Observable<DeliveryInsights> {
    if (this.insightsCache$) return this.insightsCache$;

    this.insightsCache$ = this.http
      .get<DeliveryInsights>(`${environment.apiUrl}/api/insights`)
      .pipe(
        map(data => ({
          avg_delivery_time_by_service: (data.avg_delivery_time_by_service ?? []).map(item => ({
            service_type: item.service_type,
            avg_hours: Number(item.avg_hours) || 0,
          })),
          on_time_percentage: Number(data.on_time_percentage) || 0,
          delivery_volume_30d: (data.delivery_volume_30d ?? []).map(item => ({
            date: item.date,
            count: Number(item.count) || 0,
          })),
          top_routes: (data.top_routes ?? []).map(item => ({
            origin: item.origin,
            destination: item.destination,
            count: Number(item.count) || 0,
          })),
          delay_breakdown: (data.delay_breakdown ?? []).map(item => ({
            reason: item.reason,
            count: Number(item.count) || 0,
          })),
        })),
        catchError(() => of({
          avg_delivery_time_by_service: [],
          on_time_percentage: 0,
          delivery_volume_30d: [],
          top_routes: [],
          delay_breakdown: [],
        })),
        shareReplay(1),
      );

    return this.insightsCache$;
  }
}
