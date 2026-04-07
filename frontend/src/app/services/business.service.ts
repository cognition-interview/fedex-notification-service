import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, BehaviorSubject } from 'rxjs';
import { catchError, shareReplay } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { Business } from '../models/business.model';

@Injectable({ providedIn: 'root' })
export class BusinessService {
  private selectedBusiness$ = new BehaviorSubject<string>('');
  private businessesCache = new Map<string, Observable<{ businesses: Business[]; total: number }>>();
  private businessByIdCache = new Map<string, Observable<Business | undefined>>();

  constructor(private http: HttpClient) {}

  getSelectedBusinessId(): Observable<string> {
    return this.selectedBusiness$.asObservable();
  }

  setSelectedBusinessId(id: string): void {
    this.selectedBusiness$.next(id);
  }

  getBusinesses(page = 1, limit = 10): Observable<{ businesses: Business[]; total: number }> {
    const key = `${page}:${limit}`;
    const cached = this.businessesCache.get(key);
    if (cached) return cached;

    const request$ = this.http
      .get<{ businesses: Business[]; total: number }>(
        `${environment.apiUrl}/api/businesses`,
        { params: { page: page.toString(), limit: limit.toString() } }
      )
      .pipe(
        catchError(() => of({ businesses: [], total: 0 })),
        shareReplay(1),
      );

    this.businessesCache.set(key, request$);
    return request$;
  }

  getBusinessById(id: string): Observable<Business | undefined> {
    const cached = this.businessByIdCache.get(id);
    if (cached) return cached;

    const request$ = this.http
      .get<Business>(`${environment.apiUrl}/api/businesses/${id}`)
      .pipe(
        catchError(() => of(undefined)),
        shareReplay(1),
      );

    this.businessByIdCache.set(id, request$);
    return request$;
  }
}
